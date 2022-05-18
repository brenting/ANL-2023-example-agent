import os
from collections import defaultdict
from typing import List, cast, Set

import plotly.graph_objects as go
from geniusweb.bidspace.pareto.GenericPareto import GenericPareto
from geniusweb.bidspace.pareto.ParetoLinearAdditive import ParetoLinearAdditive
from geniusweb.issuevalue.Bid import Bid
from geniusweb.party.DefaultParty import DefaultParty
from geniusweb.profile.utilityspace.LinearAdditive import LinearAdditive
from geniusweb.profileconnection.ProfileConnectionFactory import ProfileConnectionFactory
from geniusweb.profileconnection.ProfileInterface import ProfileInterface
from uri.uri import URI


def compute_pareto_frontier(settings_profiles: List[str]):
    profiles = dict()
    for profile_url in [f"file:{x}" for x in settings_profiles]:
        profileInt: ProfileInterface = ProfileConnectionFactory.create(
            URI(profile_url), DefaultParty.getReporter)
        profile: LinearAdditive = cast(LinearAdditive, profileInt.getProfile())
        profiles[profile_url] = profile

    pareto: ParetoLinearAdditive = ParetoLinearAdditive(list(profiles.values()))
    pareto_points: Set[Bid] = pareto.getPoints()

    pareto_frontier = dict()
    for pareto_bid in pareto_points:
        pareto_frontier[pareto_bid] = dict()
        for profile_name, profile in profiles.items():
            pareto_frontier[pareto_bid][profile_name] = float(profile.getUtility(pareto_bid))

    return pareto_frontier

def plot_pareto(results_trace: dict, pareto_frontier: dict, plot_file: str):
    utilities = defaultdict(lambda: {"x": [], "y": [], "bids": []})
    profiles = results_trace["connections"]
    x_axis = profiles[0]
    x_label = "_".join(x_axis.split("_")[-2:])
    y_axis = profiles[1]
    y_label = "_".join(y_axis.split("_")[-2:])

    accept = {"x": [], "y": [], "bids": []}
    for action in results_trace["actions"]:
        if "Offer" in action:
            offer = action["Offer"]
            actor = offer["actor"]
            for agent, util in offer["utilities"].items():
                if agent == x_axis:
                    utilities[actor]["x"].append(util)
                else:
                    utilities[actor]["y"].append(util)

            utilities[actor]["bids"].append(offer["bid"]["issuevalues"])

        elif "Accept" in action:
            offer = action["Accept"]
            actor = offer["actor"]
            for agent, util in offer["utilities"].items():
                if agent == x_axis:
                    accept["x"].append(util)
                else:
                    accept["y"].append(util)

            accept["bids"].append(offer["bid"]["issuevalues"])

    fig = go.Figure()
    fig.add_trace(
        go.Scatter(
            mode="markers",
            x=accept["x"],
            y=accept["y"],
            name="agreement",
            marker={"color": "green", "size": 15},
            hoverinfo="skip",
        )
    )

    color = {0: "red", 1: "blue"}
    for i, (agent, utility) in enumerate(utilities.items()):
        name = "_".join(agent.split("_")[-2:])

        text = []
        for bid, util_x, util_y in zip(utility["bids"], utility["x"], utility["y"]):
            text.append(
                "<br>".join(
                    [x_label + f"<b>: {util_x:.3f}</b><br>"]
                    + [y_label + f"<b>: {util_y:.3f}</b><br>"]
                    + [f"{i}: {v}" for i, v in bid.items()]
                )
            )

        fig.add_trace(
            go.Scatter(
                x=utility["x"],
                y=utility["y"],
                marker={"color": color[i]},
                name=f"{name}",
                hovertext = text,
                hoverinfo = "text"
            )
        )

    x_axis_profile = None
    y_axis_profile = None
    party_profiles = results_trace["partyprofiles"]
    for party_prof in party_profiles:
        if x_axis in party_prof:
            x_axis_profile = party_profiles[x_axis]["profile"]
        elif y_axis in party_prof:
            y_axis_profile = party_profiles[y_axis]["profile"]

    pareto_bids = {"x": [], "y": [], "bids": []}
    for bid, utilities in pareto_frontier.items():
        for profile, util in utilities.items():
            if profile == x_axis_profile:
                pareto_bids["x"].append(util)
            elif profile == y_axis_profile:
                pareto_bids["y"].append(util)

        pareto_bids["bids"].append(bid)

    fig.add_trace(
        go.Scatter(
            x=pareto_bids["x"],
            y=pareto_bids["y"],
            mode='markers',
            name='pareto frontier point'
        )
    )

    fig.update_layout(
        width=800,
        height=800,
        legend={
            "yanchor": "bottom",
            "y": 1,
            "xanchor": "left",
            "x": 0,
        },
    )

    fig.update_layout(title_text='Negotiation traces', title_x=0.5)
    fig.update_xaxes(title_text="Utility of " + x_label, ticks="outside")
    fig.update_yaxes(title_text="Utility of " + y_label, ticks="outside")
    fig.write_html(f"{os.path.splitext(plot_file)[0]}.html")
