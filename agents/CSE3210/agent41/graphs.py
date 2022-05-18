import json

import plotly.graph_objects as go


def get_pareto_frontier(data):
    x = []
    y = []
    pareto = data["pareto_front"]
    for case in pareto:
        print(case)
        x.append(case['utility'][0])
        y.append(case['utility'][1])
    return x, y


def get_kalai(data):
    kalai = data["kalai"]
    return kalai["utility"][0], kalai["utility"][1]


def get_nash(data):
    nash = data["nash"]
    return nash["utility"][0], nash["utility"][1]


def sketch_domain(domain):
    """
    Sketch the domain, including the Nash product, Kalai-Smorodinsky and Pareto frontier.
    """
    with open(f"domains/{domain}/specials.json") as specials:
        data = json.load(specials)

        # sketch pareto frontier
        pareto_coords = get_pareto_frontier(data)
        pareto_trace = go.Scatter(x=pareto_coords[0], y=pareto_coords[1],
                                  mode='lines',
                                  name='Pareto Frontier')
        # sketch kalai-smorodinsky
        kalai_coords = get_kalai(data)
        kalai_trace = go.Scatter(x=[kalai_coords[0]], y=[kalai_coords[1]], mode='markers',
                                 name='Kalai-Smorodinsky')
        # sketch nash product
        nash_coords = get_nash(data)
        nash_trace = go.Scatter(x=[nash_coords[0]], y=[nash_coords[1]], mode='markers',
                                name="Nash Product")

        # set up the graph
        fig = go.Figure(pareto_trace)
        fig.add_trace(kalai_trace)
        fig.add_trace(nash_trace)
        fig.update_layout(xaxis_title="profile B utility",
                          yaxis_title="profile A utility",
                          font=dict(size=18),
                          showlegend=True,
                          legend=dict(x=0.85, y=1, font=dict(size=16, color="black")), )
        fig.update_yaxes(range=[0, 1])
        fig.update_xaxes(range=[0, 1])
        fig.update_traces(marker=dict(size=18,
                                      line=dict(width=2,
                                                color='DarkSlateGrey')),
                          selector=dict(mode='markers')
                          )
        return fig


def sketch_negotiations(domain_fig, result_trace):
    """
    Sketch the utilities of the bids offered by both agents during the negotiations.
    """
    with open(result_trace) as results:

        agent1_coords = [[], []]
        agent2_coords = [[], []]
        final_coords = [[], []]
        results_data = json.load(results)

        agent1 = results_data['connections'][0]
        agent1_name = agent1[:-2].rpartition('_')[2]
        agent2 = results_data['connections'][1]
        agent2_name = agent2[:-2].rpartition('_')[2]

        for action in results_data['actions']:
            if 'Offer' in action.keys():
                offer = action['Offer']
                if offer['actor'] == agent1:
                    agent1_coords[0].append(list(offer["utilities"].values())[0])
                    agent1_coords[1].append(list(offer["utilities"].values())[1])
                else:
                    agent2_coords[0].append(list(offer["utilities"].values())[0])
                    agent2_coords[1].append(list(offer["utilities"].values())[1])
            else:
                final_coords[0] = list(action['Accept']['utilities'].values())[0]
                final_coords[1] = list(action['Accept']['utilities'].values())[1]
        agent1_trace = go.Scatter(x=agent1_coords[0], y=agent1_coords[1], mode='markers+lines',
                                  name=agent1_name)
        agent2_trace = go.Scatter(x=agent2_coords[0], y=agent2_coords[1], mode='markers+lines',
                                  name=agent2_name)
        final_point = go.Scatter(x=[final_coords[0]], y=[final_coords[1]], mode='markers',
                                 name="Accepted offer", marker=dict(size=15,
                                                                    line=dict(width=2,
                                                                              color='DarkSlateGrey')), )
        domain_fig.add_trace(agent1_trace)
        domain_fig.add_trace(agent2_trace)
        domain_fig.add_trace(final_point)
        domain_fig.update_layout(xaxis_title=f"{agent1_name} utility",
                                 yaxis_title=f"{agent2_name} utility", )
        domain_fig.show()

        return domain_fig


if __name__ == "__main__":
    domain_fig = sketch_domain("domain02")
    final_fig = sketch_negotiations(domain_fig, "results/results_trace.json")
