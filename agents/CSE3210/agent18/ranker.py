import sys

import numpy as np


# Function of the metric to use
# data -> dictionary of collected information
# output -> dictionary of each agent with a float metric assigned to them, and the counter
def metric(data):
    ranking = {}
    # Utility averages in domains
    utilities = dict()
    welfare = dict()
    for result in data:
        for thing in result:
            counter = sys.maxsize
            for key in thing:
                if 'agent_' in key:
                    temp = key.split('_')
                    if int(temp[1]) < counter:
                        counter = int(temp[1])
            if thing['result'] != 'failed':
                first_agent = thing['agent_' + str(counter)]
                other_agent = thing['agent_' + str(counter + 1)]
                if other_agent not in utilities:
                    utilities[other_agent] = []
                    welfare[other_agent] = []
                if first_agent not in utilities:
                    utilities[first_agent] = []
                    welfare[first_agent] = []
                utilities[first_agent].append(thing['utility_' + str(counter)])
                welfare[first_agent].append(thing['social_welfare'])
                utilities[other_agent].append(thing['utility_' + str(counter + 1)])
                welfare[other_agent].append(thing['social_welfare'])
    # Metric of Z-Score of each agent
    # Ideal mean should be 0.75
    ideal_utility = 0.75
    ideal_welfare = 1.2
    for agent in utilities:
        utility_mean = np.mean(utilities[agent])
        welfare_mean = np.mean(welfare[agent])
        utility_std = np.std(utilities[agent])
        welfare_std = np.std(welfare[agent])
        z_score_utility = (utility_mean - ideal_utility) / max(0.0001, utility_std)
        z_score_welfare = (welfare_mean - ideal_welfare) / max(0.0001, welfare_std)
        # Average Z-score between Z-score of utility and Z-score of welfare
        ranking[agent] = (z_score_utility + z_score_welfare) / 2
    return ranking
