"""
parameters.py — Lädt experiment.yaml und stellt ExperimentConfig bereit.

Die zentrale YAML kann für einzelne Werte per CLI überschrieben werden.
ExperimentConfig wird in SimulationConfig überführt, wenn ein einzelner
Lauf gestartet wird; für Batch-Läufe werden die batch-Felder direkt an
run_batch() / run_parallel() weitergereicht.

Fehlendes PyYAML → verständliche Fehlermeldung mit Installationshinweis.
"""

from dataclasses import dataclass, field
from pathlib import Path

from config import SimulationConfig


try:
    import yaml
except ImportError:
    yaml = None


@dataclass
class ExperimentConfig:
    # Einzelsimulation
    disruption_position_m: float = 5000.0
    disruption_lap: int = 5
    num_agents: int = 3
    num_trains: int = 1
    step_length_s: float = 1.0
    use_gui: bool = True

    # Agent
    agent_walk_speed_ms: float = 3.33
    agent_reaction_time_s: float = 90.0

    # Batch
    batch_positions_step_m: int = 25
    batch_positions_max_m: int = 15_125
    batch_agent_counts: list[int] = field(default_factory=lambda: [1, 2, 3, 4, 5, 6, 7, 8, 9, 10])
    batch_train_counts: list[int] = field(default_factory=lambda: [1])
    batch_disruption_lap: int = 5
    batch_step_length_s: float = 1.0
    batch_wall_timeout_s: int = 90
    batch_num_workers: int | None = None
    batch_zub_max_trains: int = 10

    # Logging
    logging_level: str = "INFO"
    logging_console: bool = True
    logging_file: str | None = "output/log/run.log"

    def to_simulation_config(self) -> SimulationConfig:
        """Baut eine SimulationConfig für den Einzellauf."""
        cfg = SimulationConfig(
            disruption_position_m=self.disruption_position_m,
            disruption_lap=self.disruption_lap,
            num_agents=self.num_agents,
            num_trains=self.num_trains,
            step_length_s=self.step_length_s,
            use_gui=self.use_gui,
            agent_walk_speed_ms=self.agent_walk_speed_ms,
            agent_reaction_time_s=self.agent_reaction_time_s,
        )
        return cfg

    def batch_positions(self) -> list[int]:
        """Positionen-Liste laut batch-Einstellungen."""
        return list(range(0, self.batch_positions_max_m,
                          self.batch_positions_step_m))


DEFAULT_YAML = Path(__file__).resolve().parent / "experiment.yaml"


def load_experiment(yaml_path: Path | str | None = None) -> ExperimentConfig:
    """
    Lädt experiment.yaml und gibt eine ExperimentConfig zurück.

    Fehlende Datei oder fehlendes PyYAML → Defaults werden benutzt.
    """
    path = Path(yaml_path) if yaml_path else DEFAULT_YAML

    if yaml is None:
        print("WARNUNG: PyYAML nicht installiert — nutze Defaults. "
              "Installiere es mit: pip install pyyaml")
        return ExperimentConfig()

    if not path.exists():
        print(f"WARNUNG: {path} nicht gefunden — nutze Defaults.")
        return ExperimentConfig()

    with open(path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}

    sim = data.get("simulation", {}) or {}
    agent = data.get("agent", {}) or {}
    batch = data.get("batch", {}) or {}
    logcfg = data.get("logging", {}) or {}

    return ExperimentConfig(
        disruption_position_m=float(sim.get("disruption_position_m", 5000.0)),
        disruption_lap=int(sim.get("disruption_lap", 5)),
        num_agents=int(sim.get("num_agents", 3)),
        num_trains=int(sim.get("num_trains", 1)),
        step_length_s=float(sim.get("step_length_s", 1.0)),
        use_gui=bool(sim.get("use_gui", True)),

        agent_walk_speed_ms=float(agent.get("walk_speed_ms", 3.33)),
        agent_reaction_time_s=float(agent.get("reaction_time_s", 90.0)),

        batch_positions_step_m=int(batch.get("positions_step_m", 25)),
        batch_positions_max_m=int(batch.get("positions_max_m", 15_125)),
        batch_agent_counts=list(batch.get("agent_counts", [1, 2, 3, 4, 5, 6, 7, 8, 9, 10])),
        batch_train_counts=list(batch.get("train_counts", [1])),
        batch_disruption_lap=int(batch.get("disruption_lap", 5)),
        batch_step_length_s=float(batch.get("step_length_s", 1.0)),
        batch_wall_timeout_s=int(batch.get("wall_timeout_s", 90)),
        batch_num_workers=batch.get("num_workers"),
        batch_zub_max_trains=int(batch.get("zub_max_trains", 10)),

        logging_level=str(logcfg.get("level", "INFO")),
        logging_console=bool(logcfg.get("console", True)),
        logging_file=logcfg.get("file", "output/log/run.log"),
    )


def apply_cli_overrides(exp: ExperimentConfig, args) -> ExperimentConfig:
    """
    Überschreibt ExperimentConfig-Felder mit CLI-Argumenten (falls gesetzt).

    Args:
        args: argparse.Namespace mit optionalen Feldern
              (pos, agents, trains, step_m, lap, gui, headless).
    """
    if getattr(args, "pos", None) is not None:
        exp.disruption_position_m = float(args.pos)
    if getattr(args, "agents", None) is not None:
        exp.num_agents = int(args.agents)
    if getattr(args, "trains", None) is not None:
        exp.num_trains = int(args.trains)
    if getattr(args, "lap", None) is not None:
        exp.disruption_lap = int(args.lap)
        exp.batch_disruption_lap = int(args.lap)
    if getattr(args, "step_m", None) is not None:
        exp.batch_positions_step_m = int(args.step_m)
    if getattr(args, "headless", False):
        exp.use_gui = False
    if getattr(args, "gui", False):
        exp.use_gui = True
    return exp
