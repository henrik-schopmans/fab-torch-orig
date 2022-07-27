import hydra
from examples.setup_run_snf import make_normflow_snf_model, SNFModel

from fab.target_distributions.many_well import ManyWellEnergy
import pandas as pd
import os
from omegaconf import DictConfig
import torch

from fab import FABModel, HamiltonianMonteCarlo, Metropolis
from examples.make_flow import make_wrapped_normflowdist


PATH = os.getcwd()

def load_model(cfg: DictConfig, target, model_name: str):
    dim = cfg.target.dim
    if model_name and model_name[0:3] == "snf":
        snf = make_normflow_snf_model(dim,
                                       n_flow_layers=cfg.flow.n_layers,
                                       layer_nodes_per_dim=cfg.flow.layer_nodes_per_dim,
                                       act_norm=cfg.flow.act_norm,
                                       target=target
                                       )
        if model_name:
            path_to_model = f"{PATH}/models/{model_name}.pt"
            checkpoint = torch.load(path_to_model, map_location="cpu")
            snf.load_state_dict(checkpoint['flow'])
        # wrap appropriately
        snf = SNFModel(snf, target, cfg.target.dim)
        return snf
    else:
        flow = make_wrapped_normflowdist(dim, n_flow_layers=cfg.flow.n_layers,
                                         layer_nodes_per_dim=cfg.flow.layer_nodes_per_dim,
                                         act_norm=cfg.flow.act_norm)
        path_to_model = f"{PATH}/models/{model_name}.pt"
        checkpoint = torch.load(path_to_model, map_location="cpu")
        flow._nf_model.load_state_dict(checkpoint['flow'])

        transition_operator = HamiltonianMonteCarlo(
            n_ais_intermediate_distributions=cfg.fab.n_intermediate_distributions,
            n_outer=1,
            epsilon=1.0,
            L=cfg.fab.transition_operator.n_inner_steps,
            dim=dim,
            step_tuning_method="p_accept")

        transition_operator.load_state_dict(checkpoint['trans_op'])


        model = FABModel(flow=flow,
                 target_distribution=target,
                 n_intermediate_distributions=cfg.fab.n_intermediate_distributions,
                 transition_operator=transition_operator,
                 loss_type=cfg.fab.loss_type)

        # No need to do AIS, as we aren't interested in metrics after AIS for now.
        # transition_operator = Metropolis(n_transitions=1,
        #                                  n_updates=1,
        #                                  adjust_step_size=False)

        # model = FABModel(flow=flow,
        #          target_distribution=target,
        #          n_intermediate_distributions=1,
        #          transition_operator=transition_operator,
        #          loss_type=cfg.fab.loss_type)
    return model



def evaluate(cfg: DictConfig, model_name: str, target, num_samples=int(5e4)):
    test_set_exact = target.sample((num_samples, ))
    test_set_log_prob_over_p = torch.mean(target.log_prob(test_set_exact) - target.log_Z).cpu().item()
    test_set_modes_log_prob_over_p = torch.mean(target.log_prob(target._test_set_modes) - target.log_Z)
    print(f"test set log prob under p: {test_set_log_prob_over_p:.2f}")
    print(f"modes test set log prob under p: {test_set_modes_log_prob_over_p:.2f}")
    model = load_model(cfg, target, model_name)
    eval = model.get_eval_info(num_samples, 500)
    return eval


@hydra.main(config_path="../../config", config_name="many_well.yaml")
def main(cfg: DictConfig):
    model_names = ["fab_buffer"]  # ["fab_buffer", "fab_no_buffer", "flow_kld", "flow_nis", "snf"]
    seeds = [1, 2, 3]
    num_samples = int(1e3)


    results = pd.DataFrame()
    for model_name in model_names:
        torch.set_default_dtype(torch.float32)
        torch.manual_seed(cfg.training.seed)
        target = ManyWellEnergy(cfg.target.dim, a=-0.5, b=-6, use_gpu=False)
        if cfg.training.use_64_bit:
            torch.set_default_dtype(torch.float64)
            target = target.double()
        for seed in seeds:
            name = model_name + f"_seed{seed}"
            print(f"get results for {name}")
            eval_info = evaluate(cfg, name, target, num_samples)
            eval_info.update(seed=seed,
                             model_name=model_name)
            results = results.append(eval_info, ignore_index=True)

    # Note for the SNF, that - test_set_ais_mean_log_prob is approximately the forward KL divergence,
    # if we use the normalised log prob.

    results.loc[results["model_name"] == "snf", "forward_kl"] = list((- results[results["model_name"] == "snf"]["test_set_ais_mean_log_prob"]).values)
    keys = ["eval_ess_flow", 'test_set_exact_mean_log_prob', 'test_set_modes_mean_log_prob',
            'eval_ess_ais', 'MSE_log_Z_estimate', "forward_kl"]
    print("\n *******  mean  ********************** \n")
    print(results.groupby("model_name").mean()[keys].to_latex())
    print("\n ******* std ********************** \n")
    print((results.groupby("model_name").std()[keys]).to_latex())
    results.to_csv(open("/home/laurence/work/code/FAB-TORCH/examples/paper_results/many_well/many_well_withais.csv", "w"))

    print("overall results")
    print(results[["model_name", "seed"] + keys])


if __name__ == '__main__':
    load = False
    if not load:
        main()
    else:
        results = pd.read_csv(open("many_well_with_forward_kl.csv", "r"))
        print("mean")
        print(results.groupby("model_name").mean()[["eval_ess_flow", "eval_ess_ais", "test_set_mean_log_prob"]])
        print("std")
        print(results.groupby("model_name").std()[["eval_ess_flow", "eval_ess_ais", "test_set_mean_log_prob"]])
        results.to_csv(open("gmm_results.csv", "w"))
        print("overall results")
        print(results[["model_name", "seed", "eval_ess_flow", "eval_ess_ais", "test_set_mean_log_prob"]])
