import os

import plotly.graph_objects as go
import numpy as np
from collections import defaultdict

class PlotTournament():

    def __init__(self, results_summaries, my_agent):
        self.utilities = defaultdict(list)
        self.opponent_utilities = defaultdict(list)
        self.nash_products = defaultdict(list)
        self.social_welfares = defaultdict(list)
        self.results_summaries = results_summaries
        self.my_agent = my_agent

    def update_tournament_results(self):
        for match in self.results_summaries:
            # only interested in the matches where our agent appears.
            if self.my_agent in match.values():
                agent1 = None
                util1 = None
                agent2 = None
                util2 = None
                for key in match.keys():
                    if key.startswith("agent_"):
                        if agent1 == None:
                            agent1 = match[key]
                        else:
                            agent2 = match[key]
                    if key.startswith("utility_"):
                        if util1 == None:
                            util1 = match[key]
                        else:
                            util2 = match[key]

                if agent1 != self.my_agent:
                    self.utilities[agent1].append(util2)
                    self.nash_products[agent1].append(match["nash_product"])
                    self.social_welfares[agent1].append(match["social_welfare"])

                if agent1 == self.my_agent:
                    self.opponent_utilities[agent2].append(util2)

                if agent2 != self.my_agent:
                    self.utilities[agent2].append(util1)
                    self.nash_products[agent2].append(match["nash_product"])
                    self.social_welfares[agent2].append(match["social_welfare"])

                if agent2 == self.my_agent:
                    self.opponent_utilities[agent1].append(util1)


    def plot_tournament_utilities(self, plot_file):
        self.update_tournament_results()

        x_data = list(self.utilities.keys())

        trace1 = go.Bar(
            x = x_data,
            y = [np.mean(value) for value in self.utilities.values()],
            name = self.my_agent + " Utility"
        )

        trace2 = go.Bar(
            x = x_data,
            y = [np.mean(value) for value in self.nash_products.values()],
            name = "Nash Product"
        )

        trace3 = go.Bar(
            x = x_data,
            y = [np.mean(value) for value in self.social_welfares.values()],
            name = "Social Welfare"
        )

        trace4 = go.Bar(
            x = [agent for agent in self.opponent_utilities.keys()],
            y = [np.mean(value) for value in self.opponent_utilities.values()],
            name = "Opponent Utility"
        )

        data = [trace1, trace4, trace2, trace3]

        layout = go.Layout(barmode = 'group')
        fig = go.Figure(data = data, layout = layout)

        title = "Average performance of " + self.my_agent + " against " \
                "other agents"
        fig.update_layout(title_text=title, title_x=0.5)
        fig.update_yaxes(title_text="Average Score", ticks="outside")

        fig.write_html(f"{os.path.splitext(plot_file)[0]}.html")