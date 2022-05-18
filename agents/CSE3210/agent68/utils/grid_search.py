import numpy as np
import os

from utils.runners import run_tournament
from utils.PlotTournament import PlotTournament


if not os.path.exists("results"):
    os.mkdir("results")

class TournamentInfo(PlotTournament):
  def __init__(self, results_summaries, my_agent):
    super().__init__(results_summaries, my_agent)
  
  def getTournamentInfo(self):
    self.update_tournament_results()

    utilAvgs = [np.mean(value) for value in self.utilities.values()]

    nashAvgs = [np.mean(value) for value in self.nash_products.values()]

    socialAvgs = [np.mean(value) for value in self.social_welfares.values()]

    return (np.average(utilAvgs), np.average(nashAvgs), np.average(socialAvgs))

def scoringFunction(utilScore, nashProduct, socialWelfare):
  #Normalize socialWelfare [0,2] and add more weight to utilScore?
  #Higher score == better
  return ((1.5*utilScore) + nashProduct + (socialWelfare/2))/(1.5 + 1 + 1)

e1_min = 0.1
e1_max = 0.6
e2_min = 0.1
e2_max = 0.6
e3_min = 0.1
e3_max = 0.6
utilGoalW_min = 0.4
utilGoalW_max = 1.0
leniBaseW_min = 0.0
leniBaseW_max = 0.5
step = 0.5

# with open("../results/gridSearch.csv", "w") as f:
#   f.write("")
#   f.close()
for e1 in np.arange(e1_min, e1_max, step):
  for e2 in np.arange(e2_min, e2_max, step):
    for e3 in np.arange(e3_min, e3_max, step):
      for utilGoal in np.arange(utilGoalW_min, utilGoalW_max, step):
        for leniBase in np.arange(leniBaseW_min, leniBaseW_max, step):
          tournament_settings = {
                "agents": [
                    # "agents.boulware_agent.boulware_agent.BoulwareAgent",
                    "agents.conceder_agent.conceder_agent.ConcederAgent",
                    # "agents.linear_agent.linear_agent.LinearAgent",
                    # "agents.random_agent.random_agent.RandomAgent",
                    # "agents.template_agent.template_agent.TemplateAgent",
                    "main.threephase_agent.threephase_agent.ThreePhaseAgent",
                ],
                "profile_sets": [
                    ["domains/domain00/profileA.json", "domains/domain00/profileB.json"],
                    # ["domains/domain01/profileA.json", "domains/domain01/profileB.json"],
                ],
                "deadline_rounds": 200,
                "parameters": {"e1": e1, "e2":e2, "e3":e3, "utilWeight" : utilGoal, "leniencyWeight" : (1-utilGoal), "leniencyBase" : leniBase},
          }
          # run a session and obtain results in dictionaries
          print("Touring\n", flush=True)
          tournament, results_summaries = run_tournament(tournament_settings)

          print("Calcing\n", flush=True)
          
          my_agent = "ThreePhaseAgent"
          tour = TournamentInfo(results_summaries, my_agent)
          util, nash, social = tour.getTournamentInfo()
          score = scoringFunction(util, nash, social)
          params = f'{e1},{e2},{e3},{utilGoal},{1-utilGoal},{leniBase}'
          print("Writing\n", flush=True)
          with open("results/gridSearch.csv", "a") as f:
              f.write("{},{}\n".format(params, score))
          
