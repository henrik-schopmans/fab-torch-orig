import matplotlib.pyplot as plt
import torch
import os
import pathlib
import hydra
import wandb
from omegaconf import DictConfig

from datetime import datetime


from fab import FABModel, HamiltoneanMonteCarlo, Trainer, Metropolis
from fab.utils.logging import PandasLogger, WandbLogger, Logger
from fab.utils.plotting import plot_contours, plot_marginal_pair
from examples.make_flow import make_wrapped_normflowdist


def setup_logger(cfg: DictConfig, save_path: str) -> Logger:
    if hasattr(cfg.logger, "pandas_logger"):
        logger = PandasLogger(save=True,
                              save_path=save_path + "logging_hist.csv",
                              save_period=cfg.logger.pandas_logger.save_period)
    elif hasattr(cfg.logger, "wandb"):
        logger = WandbLogger(**cfg.logger.wandb, config=dict(cfg))
    else:
        raise Exception("No logger specified, try adding the wandb or "
                        "pandas logger to the config file.")
    return logger




def _run(cfg: DictConfig):
    dim = cfg.target.dim  # applies to flow and target
    if cfg.training.use_64_bit:
        torch.set_default_dtype(torch.float64)
    torch.manual_seed(cfg.training.seed)
    current_time = datetime.now().strftime("%Y_%m_%d-%I_%M_%S_%p")
    save_path = cfg.evaluation.save_path + current_time + "/"
    logger = setup_logger(cfg, save_path)
    if hasattr(cfg.logger, "wandb"):
        # if using wandb then save to wandb path
        save_path = os.path.join(wandb.run.dir, save_path)
    pathlib.Path(save_path).mkdir(parents=True, exist_ok=False)
    with open(save_path + "config.txt", "w") as file:
        file.write(str(cfg))
    from fab.target_distributions.many_well import ManyWellEnergy
    assert dim % 2 == 0
    target = ManyWellEnergy(dim, a=-0.5, b=-6)
    plotting_bounds = (-3, 3)

    flow = make_wrapped_normflowdist(dim, n_flow_layers=cfg.flow.n_layers,
                                     layer_nodes_per_dim=cfg.flow.layer_nodes_per_dim)


    if cfg.fab.transition_operator.type == "hmc":
        # very lightweight HMC.
        transition_operator = HamiltoneanMonteCarlo(
            n_ais_intermediate_distributions=cfg.fab.n_intermediate_distributions,
            n_outer=1,
            epsilon=1.0, L=cfg.fab.transition_operator.n_inner_steps, dim=dim,
            step_tuning_method="p_accept")
    elif cfg.fab.transition_operator.type == "metropolis":
        transition_operator = Metropolis(n_transitions=cfg.fab.n_intermediate_distributions,
                                         n_updates=cfg.transition_operator.n_inner_steps,
                                         adjust_step_size=True)
    else:
        raise NotImplementedError


    # use GPU if available
    if torch.cuda.is_available() and cfg.training.use_gpu:
      flow.cuda()
      transition_operator.cuda()
      print("utilising GPU")


    fab_model = FABModel(flow=flow,
                         target_distribution=target,
                         n_intermediate_distributions=cfg.fab.n_intermediate_distributions,
                         transition_operator=transition_operator,
                         loss_type=cfg.fab.loss_type)
    optimizer = torch.optim.AdamW(flow.parameters(), lr=cfg.training.lr)
    # scheduler = torch.optim.lr_scheduler.ExponentialLR(optimizer, gamma=0.995)
    scheduler = None

    def plot(fab_model, n_samples: int = cfg.training.batch_size, dim: int = dim):
        n_rows = dim // 2
        fig, axs = plt.subplots(dim // 2, 2, sharex=True, sharey=True, figsize=(10, n_rows * 3))

        samples_flow = fab_model.flow.sample((n_samples,))
        samples_ais = fab_model.annealed_importance_sampler.sample_and_log_weights(n_samples,
                                                                                   logging=False)[0]

        for i in range(n_rows):
            plot_contours(target.log_prob_2D, bounds=plotting_bounds, ax=axs[i, 0])
            plot_contours(target.log_prob_2D, bounds=plotting_bounds, ax=axs[i, 1])

            # plot flow samples
            plot_marginal_pair(samples_flow, ax=axs[i, 0], bounds=plotting_bounds,
                               marginal_dims=(i * 2, i * 2 + 1))
            axs[i, 0].set_xlabel(f"dim {i * 2}")
            axs[i, 0].set_ylabel(f"dim {i * 2 + 1}")

            # plot ais samples
            plot_marginal_pair(samples_ais, ax=axs[i, 1], bounds=plotting_bounds,
                               marginal_dims=(i * 2, i * 2 + 1))
            axs[i, 1].set_xlabel(f"dim {i * 2}")
            axs[i, 1].set_ylabel(f"dim {i * 2 + 1}")
            plt.tight_layout()
        axs[0, 1].set_title("ais samples")
        axs[0, 0].set_title("flow samples")
        return [fig]

    # Create trainer
    trainer = Trainer(model=fab_model, optimizer=optimizer, logger=logger, plot=plot,
                      optim_schedular=scheduler, save_path=save_path)
    trainer.run(n_iterations=cfg.training.n_iterations, batch_size=cfg.training.batch_size,
                n_plot=cfg.evaluation.n_plots,
                n_eval=cfg.evaluation.n_eval, eval_batch_size=cfg.evaluation.eval_batch_size,
                save=True, n_checkpoints=cfg.evaluation.n_checkpoints)


@hydra.main(config_path="./config", config_name="many_well.yaml")
def run(cfg: DictConfig):
    _run(cfg)

if __name__ == '__main__':
    run()