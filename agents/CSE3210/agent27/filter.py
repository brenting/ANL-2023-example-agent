import json

"""
    This is a script that filters the tournament results to be easier to analyze for the report.
    Only the sessions containing our agent are left after the filtering, and the object keys are modified to be
    easier to analyze using Google Spreadsheets.
"""

json_files = [
            'results/results_summaries.json',
        ]

# concatenate all data from all the given json files before filtering
data = []
for json_file_name in json_files:
    with open(json_file_name) as json_file:
        data = data + json.load(json_file)
        json_file.close()

# first only get results relevant for agent
no_offer_accepted = 0   # keep track of how many offers were not accepted

# save only the relevant negotiation results (the results containing our agent)
relevant_negotiation_results = []

# iterate over all json objects in the data
for negotiation_result in data:
    for key, value in negotiation_result.items():
        # save the negotiation results of our agent and increment the counter of the offers that no agent accepts
        if key.startswith('agent_') and value == 'Group27_NegotiationAssignment_Agent':
            relevant_negotiation_results.append(negotiation_result)
            if negotiation_result['result'] != 'agreement':
                no_offer_accepted += 1
            break

# parse the json objects to make then easier to analyze
# make all json keys to only include agent_1, agent_2 and
# utility_1, utility_2
relevant_negotiation_results_agents_parsed = []

# for all filtered relevant negotiation results
for relevant_negotiation_result in relevant_negotiation_results:
    agent = 0
    utility = 0
    entry = {}
    for key, value in relevant_negotiation_result.items():
        # change all agent_* to agent_1 and agent_2
        if key.startswith('agent_') and agent == 0:
            entry["agent_1"] = value
            agent += 1
        elif key.startswith('agent_') and agent == 1:
            entry["agent_2"] = value
        # change all utility_* to utility_1 and utility_2
        elif key.startswith("utility_") and utility == 0:
            entry["utility_1"] = value
            utility += 1
        elif key.startswith("utility_") and utility == 1:
            entry["utility_2"] = value
        else:
            entry[key] = value
    relevant_negotiation_results_agents_parsed.append(entry)

# print the results and save then to a json file
print(relevant_negotiation_results_agents_parsed)

with open('results/results_filtered.json', 'w') as outfile:
    json.dump(relevant_negotiation_results_agents_parsed, outfile)
    outfile.close()
