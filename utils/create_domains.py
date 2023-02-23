import json
import math
import os
from itertools import product
from math import sqrt
from random import randint
from shutil import rmtree
from string import ascii_uppercase
from typing import Iterable

import numpy as np
import plotly.graph_objects as go
from numpy.random import dirichlet

NUM_DOMAINS_TO_GENERATE = 50


def main():
    for i in range(NUM_DOMAINS_TO_GENERATE):
        domain = Domain.create_random(f"domain{i:03d}")
        domain.calculate_specials()
        domain.generate_visualisation()
        domain.to_file("domains/")


class Profile:
    def __init__(self, profile, issue_weights, value_weights):
        self.profile = profile
        self.issue_weights = issue_weights
        self.value_weights = value_weights

    @classmethod
    def from_file(cls, utility_file):
        utility_file = utility_file.split(":")[-1]

        with open(utility_file, "r") as f:
            profile = json.load(f)

        raw = profile["LinearAdditiveUtilitySpace"]
        issue_weights = {i: w for i, w in raw["issueWeights"].items()}
        value_weights = {}

        for issue, values in raw["issueUtilities"].items():
            issue_value_weights = {
                v: w for v, w in values["DiscreteValueSetUtilities"]["valueUtilities"].items()
            }
            value_weights[issue] = issue_value_weights

        return cls(profile, issue_weights, value_weights)

    @classmethod
    def create_random(cls, domain, name):
        def dirichlet_dist(names, mode, alpha=1):
            distribution = (dirichlet([alpha] * len(names)) * 100000).astype(int)
            if mode == "issues":
                distribution[0] += 100000 - np.sum(distribution)
            if mode == "values":
                # distribution = [100000] + [100000 * random() for _ in range(len(names) - 1)]
                # shuffle(distribution)
                # distribution = np.array(distribution).astype(int)
                # distribution = (dirichlet(np.array(range(len(names))) * 0.3 + 1.0) * 100000).astype(int)
                # shuffle(distribution)
                distribution = distribution - np.min(distribution)
                distribution = (distribution * 100000 / np.max(distribution)).astype(
                    int
                )
            distribution = distribution / 100000
            return {i: w for i, w in zip(names, distribution)}

        issues = list(domain["issuesValues"].keys())
        issue_weights = dirichlet_dist(issues, "issues")
        value_weights = {}
        for issue in issues:
            values = domain["issuesValues"][issue]["values"]
            value_weights[issue] = dirichlet_dist(values, "values", alpha=1)

        issue_utilities = {
            i: {"DiscreteValueSetUtilities": {"valueUtilities": value_weights[i]}}
            for i in issues
        }
        profile = {
            "LinearAdditiveUtilitySpace": {
                "issueUtilities": issue_utilities,
                "issueWeights": issue_weights,
                "domain": domain,
                "name": name,
            }
        }
        return cls(profile, issue_weights, value_weights)

    def to_file(self, parent_path):
        domain_name = self.profile["LinearAdditiveUtilitySpace"]["domain"]["name"]
        profile_name = self.profile["LinearAdditiveUtilitySpace"]["name"]
        path = os.path.join(parent_path, domain_name)
        with open(os.path.join(path, f"{profile_name}.json"), "w") as f:
            f.write(json.dumps(self.profile, indent=2))

    def get_issues_values(self):
        return self.profile["LinearAdditiveUtilitySpace"]["domain"]["issuesValues"]

    def get_utility(self, bid: dict[str, str]):
        return sum(
            self.issue_weights[i] * self.value_weights[i][v] for i, v in bid.items()
        )


class Domain:
    def __init__(
        self,
        domain,
        profile_A: Profile,
        profile_B: Profile,
        SW_bid=None,
        nash_bid=None,
        kalai_bid=None,
        pareto_front=None,
        distribution=None,
        opposition=None,
        visualisation=None,
    ):
        self.domain = domain
        self.profile_A = profile_A
        self.profile_B = profile_B
        self.SW_bid = SW_bid
        self.nash_bid = nash_bid
        self.kalai_bid = kalai_bid
        self.pareto_front = pareto_front
        self.distribution = distribution
        self.opposition = opposition
        self.visualisation = visualisation

    @classmethod
    def create_random(cls, name):
        domain_size = randint(200, 10000)

        while True:
            num_issues = randint(4, 10)
            spread = dirichlet([1] * num_issues)
            multiplier = (domain_size / np.prod(spread)) ** (1.0 / num_issues)
            values_per_issue = np.round(multiplier * spread).astype(np.int32)
            values_per_issue = np.clip(values_per_issue, 2, None)
            if abs(domain_size - np.prod(values_per_issue)) < (0.1 * domain_size):
                break
        issues = list(ascii_uppercase[:num_issues])

        issuesValues = {}
        for issue, num_values in zip(issues, values_per_issue):
            values = {"values": [f"value{x}" for x in ascii_uppercase[:num_values]]}
            issuesValues[f"issue{issue}"] = values

        domain = {"name": name, "issuesValues": issuesValues}
        profile_A = Profile.create_random(domain, "profileA")
        profile_B = Profile.create_random(domain, "profileB")
        return cls(domain, profile_A, profile_B)

    @classmethod
    def from_directory(cls, directory):
        name = os.path.basename(directory)
        profile_B = Profile.from_file(f"{directory}/profileB.json")
        profile_A = Profile.from_file(f"{directory}/profileA.json")
        domain = {"name": name, "issuesValues": profile_A.get_issues_values()}

        specials_path = f"{directory}/specials.json"
        if os.path.exists(specials_path):
            with open(specials_path, "r") as f:
                specials = json.load(f)
            return cls(
                domain,
                profile_A,
                profile_B,
                SW_bid=specials["social_welfare"],
                nash_bid=specials["nash"],
                kalai_bid=specials["kalai"],
                pareto_front=specials["pareto_front"],
                distribution=specials["distribution"],
                opposition=specials["opposition"],
            )
        else:
            domain = cls(domain, profile_A, profile_B)
            return domain

    def calculate_specials(self):
        if self.nash_bid:
            return False
        self.pareto_front = self.get_pareto(list(self.iter_bids()))
        self.distribution = self.get_distribution(self.iter_bids())

        SW_utility = 0
        nash_utility = 0
        kalai_diff = 10

        for pareto_bid in self.pareto_front:
            utility_A, utility_B = pareto_bid["utility"][0], pareto_bid["utility"][1]

            utility_diff = abs(utility_A - utility_B)
            utility_prod = utility_A * utility_B
            utility_sum = utility_A + utility_B

            if utility_diff < kalai_diff:
                self.kalai_bid = pareto_bid
                kalai_diff = utility_diff
                self.opposition = sqrt((utility_A - 1.0) ** 2 + (utility_B - 1.0) ** 2)
            if utility_prod > nash_utility:
                self.nash_bid = pareto_bid
                nash_utility = utility_prod
            if utility_sum > SW_utility:
                self.SW_bid = pareto_bid
                SW_utility = utility_sum

        return True

    def generate_visualisation(self):
        bid_utils = [self.get_utilities(bid) for bid in self.iter_bids()]
        bid_utils = list(zip(*bid_utils))

        fig = go.Figure()

        fig.add_trace(
            go.Scatter(
                x=bid_utils[0],
                y=bid_utils[1],
                mode="markers",
                name="bids",
                marker=dict(size=3),
            )
        )

        if self.pareto_front:
            pareto_utils = [bid["utility"] for bid in self.pareto_front]
            pareto_utils = list(zip(*pareto_utils))
            fig.add_trace(
                go.Scatter(
                    x=pareto_utils[0],
                    y=pareto_utils[1],
                    mode="lines+markers",
                    name="Pareto",
                    marker=dict(size=3),
                    line=dict(width=1.5),
                )
            )

        if self.nash_bid:
            x, y = self.nash_bid["utility"]
            fig.add_trace(
                go.Scatter(
                    x=[x],
                    y=[y],
                    mode="markers",
                    name="Nash",
                    marker=dict(size=8, line_width=2, symbol="x-thin"),
                )
            )

        if self.kalai_bid:
            x, y = self.kalai_bid["utility"]
            fig.add_trace(
                go.Scatter(
                    x=[x],
                    y=[y],
                    mode="markers",
                    name="Kalai-Smorodinsky",
                    marker=dict(size=8, line_width=2, symbol="cross-thin"),
                )
            )

        fig.update_xaxes(range=[0, 1], title_text="Utility A")
        fig.update_yaxes(range=[0, 1], title_text="Utility B")

        fig.update_layout(
            title=dict(
                text=f"{self.get_name()}<br><sub>(size: {len(list(self.iter_bids()))}, opposition: {self.opposition:.4f}, distribution: {self.distribution:.4f})</sub>",
                x=0.5,
                xanchor="center",
            )
        )

        self.visualisation = fig

    def to_file(self, parent_path):
        path = os.path.join(parent_path, self.domain["name"])
        if os.path.exists(path):
            rmtree(path)
        os.makedirs(path)

        with open(os.path.join(path, f"{self.domain['name']}.json"), "w") as f:
            f.write(json.dumps(self.domain, indent=2))
        self.profile_A.to_file(parent_path)
        self.profile_B.to_file(parent_path)

        if self.nash_bid:
            with open(os.path.join(path, "specials.json"), "w") as f:
                f.write(
                    json.dumps(
                        {
                            "size": len(list(self.iter_bids())),
                            "opposition": self.opposition,
                            "distribution": self.distribution,
                            "social_welfare": self.SW_bid,
                            "nash": self.nash_bid,
                            "kalai": self.kalai_bid,
                            "pareto_front": self.pareto_front,
                        },
                        indent=2,
                    )
                )

        if self.visualisation:
            self.visualisation.write_image(
                file=os.path.join(path, "visualisation.pdf"), scale=5
            )

    def iter_bids(self) -> Iterable:
        return iter(self)

    def get_utilities(self, bid):
        return self.profile_A.get_utility(bid), self.profile_B.get_utility(bid)

    def get_pareto(self, all_bids: list):
        pareto_front = []
        # dominated_bids = set()
        while True:
            candidate_bid = all_bids.pop(0)
            bid_nr = 0
            dominated = False
            while len(all_bids) != 0 and bid_nr < len(all_bids):
                bid = all_bids[bid_nr]
                if self._dominates(candidate_bid, bid):
                    # If it is dominated remove the bid from all bids
                    all_bids.pop(bid_nr)
                    # dominated_bids.add(frozenset(bid.items()))
                elif self._dominates(bid, candidate_bid):
                    dominated = True
                    # dominated_bids.add(frozenset(candidate_bid.items()))
                    bid_nr += 1
                else:
                    bid_nr += 1

            if not dominated:
                # add the non-dominated bid to the Pareto frontier
                pareto_front.append(
                    {
                        "bid": candidate_bid,
                        "utility": [
                            self.profile_A.get_utility(candidate_bid),
                            self.profile_B.get_utility(candidate_bid),
                        ],
                    }
                )

            if len(all_bids) == 0:
                break

        pareto_front = sorted(pareto_front, key=lambda d: d["utility"][0])

        return pareto_front

    def get_distribution(self, bids_iter) -> float:
        min_distance_sum = 0.0

        for i, bid in enumerate(bids_iter):
            min_distance = self.distance_to_pareto(bid)
            min_distance_sum += min_distance

        distribution = min_distance_sum / (i + 1)

        return distribution

    def _dominates(self, bid, candidate_bid):
        if self.profile_A.get_utility(bid) < self.profile_A.get_utility(candidate_bid):
            return False
        elif self.profile_B.get_utility(bid) < self.profile_B.get_utility(
            candidate_bid
        ):
            return False
        else:
            return True

    def distance_to_pareto(self, bid):
        if not self.pareto_front:
            raise ValueError("Pareto front not calculated")

        min_distance = 5.0
        for pareto_element in self.pareto_front:
            pareto_bid = pareto_element["bid"]
            distance = self.distance(pareto_bid, bid)
            if distance < min_distance:
                min_distance = distance

        return min_distance

    def distance(self, bid1, bid2=None):
        """calculate Euclidian distance in terms of utility between a bid and 0 or between two bids.

        Args:
            bid1 (dict[str, str]): bid dictionary where keys are issues and values are the values
            bid2 (dict[str, str], optional): see bid1. Defaults to None.

        Returns:
            float: Euclidian distance
        """
        if bid2 and bid1:
            a = (self.profile_A.get_utility(bid1) - self.profile_A.get_utility(bid2)) ** 2
            b = (self.profile_B.get_utility(bid1) - self.profile_B.get_utility(bid2)) ** 2
        elif bid1:
            a = self.profile_A.get_utility(bid1) ** 2
            b = self.profile_B.get_utility(bid1) ** 2
        else:
            raise ValueError("receive None bid")
        return math.sqrt(a + b)

    def get_name(self):
        return self.domain["name"]

    def __iter__(self) -> dict:
        issuesValues = [
            [i, v["values"]] for i, v in self.domain["issuesValues"].items()
        ]
        issues, values = zip(*issuesValues)

        bids_values = product(*values)
        for bid_values in bids_values:
            yield {i: v for i, v in zip(issues, bid_values)}

    def __str__(self) -> str:
        return str(self.domain)


if __name__ == "__main__":
    main()
