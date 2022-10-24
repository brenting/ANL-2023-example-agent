import json
import os
from pathlib import Path
import time
import shutil
from utils.runners import run_competition


def main(tournament_settings):
    if not "tag" in tournament_settings:
        tournament_settings["tag"] = time.strftime('%Y%m%d-%H%M%S')

    if os.path.exists("work_dir/dask_slurm_output"):
        shutil.rmtree("work_dir/dask_slurm_output")

    RESULTS_DIR = Path("work_dir/results", tournament_settings["tag"])
    STATES_DIR = Path("work_dir/states", tournament_settings["tag"])

    if RESULTS_DIR.exists():
        shutil.rmtree(RESULTS_DIR)

    # create results directory if it does not exist
    if not RESULTS_DIR.exists():
        RESULTS_DIR.mkdir(parents=True)
        traces_dir = RESULTS_DIR / "traces"
        traces_dir.mkdir(parents=True)

    if not STATES_DIR.exists():
        STATES_DIR.mkdir(parents=True)


    # run a session and obtain results in dictionaries
    tournament_steps, tournament_results, tournament_results_summary = run_competition(tournament_settings, STATES_DIR, RESULTS_DIR)

    # save the tournament settings for reference
    # with open(RESULTS_DIR.joinpath("tournament_steps.json"), "w", encoding="utf-8") as f:
    #     f.write(json.dumps(tournament_steps, indent=2))
    # save the tournament results
    with open(RESULTS_DIR.joinpath("tournament_results.json"), "w", encoding="utf-8") as f:
        f.write(json.dumps(tournament_results, indent=2))
    # save the tournament results summary
    tournament_results_summary.to_csv(RESULTS_DIR.joinpath("tournament_results_summary.csv"))


if __name__ == "__main__":
    # general settings
    agents= [
        "agents.ANL2022.Agent007",
        "agents.ANL2022.Agent4410",
        "agents.ANL2022.AgentFO2",
        "agents.ANL2022.AgentFish",
        "agents.ANL2022.BIU_agent",
        "agents.ANL2022.ChargingBoul",
        "agents.ANL2022.CompromisingAgent",
        "agents.ANL2022.DreamTeam109Agent",
        "agents.ANL2022.GEAAgent",
        "agents.ANL2022.LearningAgent",
        "agents.ANL2022.LuckyAgent2022",
        "agents.ANL2022.MiCROAgent",
        "agents.ANL2022.Pinar_Agent",
        "agents.ANL2022.ProcrastinAgent",
        "agents.ANL2022.RGAgent",
        "agents.ANL2022.SmartAgent",
        "agents.ANL2022.SuperAgent",
        "agents.ANL2022.ThirdAgent",
        "agents.ANL2022.Tjaronchery10Agent",
    ]
    deadline_time_ms = 60000
    num_rounds = 50
    self_play = True

    # session specific settings
    settings_list = []
    for i in range(10):
        learning = True if i < 5 else False
        tournament_settings = {
            "agents": agents,
            "tag": f"AIJ_run-{i + 1:03}_learning-{learning}_self-play-{self_play}",
            "learning": learning,
            "deadline_time_ms": deadline_time_ms,
            "num_rounds": num_rounds,
            "self_play": self_play,
        }
        settings_list.append(tournament_settings)

    for tournament_settings in settings_list:
        main(tournament_settings)

        # delay to give cluster time to close
        time.sleep(60)