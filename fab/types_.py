from typing import Callable, Tuple, Mapping, Any, Iterator
import torch
import abc

LogProbFunc = Callable[[torch.Tensor], torch.Tensor]


class Distribution(abc.ABC):
    """Used for distributions that have a defined sampling and log probability function."""
    @abc.abstractmethod
    def log_prob(self, x: torch.Tensor) -> torch.Tensor:
        raise NotImplementedError

    @abc.abstractmethod
    def sample_and_log_prob(self, shape: Tuple) -> Tuple[torch.Tensor, torch.Tensor]:
        raise NotImplementedError

    @abc.abstractmethod
    def sample(self, shape: Tuple) -> torch.Tensor:
        """Returns samples from the model."""
        raise NotImplementedError

    @property
    @abc.abstractmethod
    def event_shape(self) -> Tuple[int, ...]:
        """Shape of a single sample."""
        raise NotImplementedError


class Model(object):
    # TODO: define signatures of save and load, add docstring

    @abc.abstractmethod
    def loss(self, batch_size: int) -> torch.Tensor:
        raise NotImplementedError

    def get_iter_info(self) -> Mapping[str, Any]:
        """Return information from latest loss iteration, for use in logging."""
        raise NotImplementedError

    def eval(self) -> Mapping[str, Any]:
        """Evaluate the model at the current point in training. This is useful for more expensive
        evaluation metrics than what is computed in get_iter_info."""

    def parameters(self) -> Iterator[torch.nn.Parameter]:
        """Returns the tunable parameters of the model for use inside the train loop. This is
        required for gradient norm clipping."""

    def save(self):
        raise NotImplementedError

    def load(self):
        raise NotImplementedError
