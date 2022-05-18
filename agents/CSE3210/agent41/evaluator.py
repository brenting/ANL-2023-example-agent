import sys
import os
import utils.runners
import itertools
import json
import numpy as np
from alive_progress import alive_bar


our_agent = "agents.orange_agent.orange_agent.OrangeAgent"

agents = [
    "agents.boulware_agent.boulware_agent.BoulwareAgent",
    "agents.linear_agent.linear_agent.LinearAgent",
    "agents.gamer_agent.gamer_agent.GamerAgent",
    "agents.shreker.shreker.Shreker",
    "agents.hope_agent.hope_agent.HopeAgent",
]

param_grid = [
  [0.0,0.2,0.4],
  [0.1,0.25],
  [0.5,0.8],
  [0.6,0.8],
  [0.9,0.95],
  [0.9,0.95],
  [0.1,0.2],
  [0.00025,0.0005],
  [0.00075,0.001],
  [0.00125,0.002],
  [0.4,0.5,0.6]
]

def conf_to_json(conf, name):
  data = {
    "util_adv_from_accept" : conf[0],
    "util_adv_from_offer" : conf[1],
    "util_adv_to_offer" : conf[2],
    "progress_mid" : conf[3],
    "progress_fast": conf[4],
    "utility_range_from" : conf[5],
    "utility_range_to" : conf[5] + conf[6],
    "slow_decrease" : conf[7],
    "mid_decrease" : conf[8],
    "fast_decrease" : conf[9],
    "minimal_reservation_val": conf[10]
  }
  if name is None:
    name = "params.json"
  with open(name, 'w', encoding='utf-8') as f:
    json.dump(data, f, ensure_ascii=False, indent=2)

class HiddenPrints:
    def __enter__(self):
        self._original_stdout = sys.stdout
        sys.stdout = open(os.devnull, 'w')

    def __exit__(self, exc_type, exc_val, exc_tb):
        sys.stdout.close()
        sys.stdout = self._original_stdout

max_wins = 0
avg_sw = 0
winning_conf = {}

iters = 1
for arr in param_grid:
  iters *= len(arr)

confs = itertools.product(*param_grid)
i = 0

bar = alive_bar(iters)

with alive_bar(iters) as bar:
  for conf in confs:
      i += 1
      conf_to_json(conf, None)

      curr_wins = 0
      social_welfare = []
      for agent in agents:
        settings = {
          "agents": [
              our_agent,
              agent
          ],
          "profiles": ["domains/domain00/profileA.json", "domains/domain00/profileB.json"],
          "deadline_rounds": 200,
        }

        _, results_summary = utils.runners.run_session(settings)

        if results_summary["result"] != "ERROR":
          social_welfare.append(results_summary['social_welfare'])
        if results_summary["result"] != "ERROR" and results_summary['utility_1'] > results_summary['utility_2']:
          curr_wins += 1

      sw = np.average(social_welfare)

      if curr_wins > max_wins or (curr_wins == max_wins and sw > avg_sw):
        max_wins = curr_wins
        avg_sw = sw
        winning_conf = conf
        print("NEW WINNING CONF WITH {} WINS IS WITH AVG SOCIAL WELFARE OF {}:".format(max_wins, sw))
        print(json.dumps(winning_conf, indent=2))
        conf_to_json(conf, "best.json")
      bar()



conf_to_json(winning_conf, "params.json")
print("WINNING CONF WITH {} WINS IS:".format(max_wins))
print(json.dumps(winning_conf, indent=2))