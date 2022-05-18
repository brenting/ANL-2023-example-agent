import math
import time
from typing import List, Set, Dict

from geniusweb.issuevalue.Bid import Bid
from geniusweb.issuevalue.Domain import Domain
from geniusweb.issuevalue.Value import Value
from geniusweb.profile.Profile import Profile


class AgentUtility:

    def __init__(self, profile: Profile = None, progress=None):
        self._profile = profile
        self._progress = progress
        self._self_bid_history = []
        self._opponent_weight_heuristic = {}
        self._issue_count_dict: Dict[str, Dict[Value, int]] = None

    def set_profile(self, profile: Profile):
        self._profile = profile
        self._intialize_weights()
        self._initialize_opponent_issue_count()

    def set_progress(self, progress):
        self._progress = progress

    def get_weight_heuristic(self):
        return self._opponent_weight_heuristic

    def _intialize_weights(self):
        """"
        Initializes the _opponent_weight_heuristic with values that are equally divided over the issues
        If there are 2 issues then the initial weight heuristic becomes {(issue1 : 0.5), (issue2: 0.5)} 
        """""
        weightDict = self._profile.getProfile().getWeights()
        weightList = []
        for key, value in weightDict.items():
            weightList.append((key, value))
        # sort the weights in decending order
        self.weights = sorted(weightList, key=lambda tup: tup[1], reverse=True)

        # instantiate opponent_weights heuristic
        heuristic_weights_dict = weightDict
        initialWeightDistribution: float = 1 / len(heuristic_weights_dict.items())
        for key, value in heuristic_weights_dict.items():
            heuristic_weights_dict[key] = initialWeightDistribution
        self._opponent_weight_heuristic = heuristic_weights_dict

    def _initialize_opponent_issue_count(self):
        """""
        Initializes an empty _issue_count_dict
        """""
        domain: Domain = self._profile.getProfile().getDomain()
        issues: Set[str] = domain.getIssues()

        self._issue_count_dict: Dict[str, Dict[Value, int]] = {}
        for issue in issues:
            self._issue_count_dict[issue]: Dict[Value, int] = {}
            for value in domain.getValues(issue):
                self._issue_count_dict[issue][value] = 0

    def get_bid_history(self):
        """""
        returns the bid history
        """""
        return self._self_bid_history

    def speed_factor(self):
        """""
        returns progress multiplied by a constant
        """""
        return math.ceil(self._progress.get(time.time() * 1000) * 50)

    def update_opponent_issue_count(self, bid):
        """""
        Updates the empty _issue_count_dict, by incrementing the counter of that value in each issue of the bid
        """""
        for issue, value in bid.getIssueValues().items():
            self._issue_count_dict[issue][value] += 1

    def get_opponent_issue_count(self):
        """""
        Get the normalized _issue_count_dict, it does this by dividing the occurence count of the value by the max occurence count of a value in that issue. 
        This is done for each issue.
        """""
        
        normalized_opponent_issue_count: Dict[str, Dict[Value, float]] = {}

        for issue in self._issue_count_dict:
            normalized_opponent_issue_count[issue] = {}
            total_issues: int = max(self._issue_count_dict[issue].values())
            division_factor = total_issues if total_issues != 0 else 1
            for value in self._issue_count_dict[issue]:
                normalized_opponent_issue_count[issue][value] = self._issue_count_dict[issue][value] / division_factor

        return normalized_opponent_issue_count

    def update_opponent_weight_heuristic(self, bid: Bid):
        """"
        This method updates the opponent weight heuristic accordingly so that the total weight is always 1
        if issues values are changed we decrease the weight, if they stay the same we increase the weight'
        "q" is the size of tee changes we make to the weights
        """
        if len(self._self_bid_history) > 2:
            prev_bid = self._self_bid_history[len(self._self_bid_history) - 3][0]
        else:
            return

        CONSTANT_q = 0.1
        # If issues get changed a lot then they are probably less important to the opponents
        bidIssueValues = bid.getIssueValues()
        prevBidIssueValues = prev_bid.getIssueValues()
        differentIssueKeys: [str] = []
        sameIssueKeys: [str] = []

        for key, value in bidIssueValues.items():
            # to make sure that the weight stays between 0 and 1 there are extra conditions to see
            # if the weight of that particular issue can be further incremented or decremented so we don't go above 1 or below 0
            if value != prevBidIssueValues[key] and self._opponent_weight_heuristic[key] > 0 + CONSTANT_q:
                differentIssueKeys.append(key)
            elif self._opponent_weight_heuristic[key] < 1 - CONSTANT_q:
                sameIssueKeys.append(key)

        # if all the issue values change or if none of the values change don't update the heuristic,
        if len(sameIssueKeys) != 0 and len(differentIssueKeys) != 0:
            for key, value in self._opponent_weight_heuristic.items():
                if key in differentIssueKeys:
                    self._opponent_weight_heuristic[key] -= (CONSTANT_q / len(
                        differentIssueKeys))  # self._opponent_weight_heuristic[key] * n #(n / len(differentIssueKeys))
                else:
                    self._opponent_weight_heuristic[key] += (CONSTANT_q / len(
                        sameIssueKeys))  # self._opponent_weight_heuristic[key] * n # (n / len(sameIssueKeys))

    def append_to_bid_history(self, bid: Bid, own_bid):
        """""
        Adds a bid to the bid history
        """""
        self._self_bid_history.append((bid, self._profile.getProfile().getUtility(bid), own_bid))

    def get_last_own_bid_utility(self):
        """""
        returns the utility of the last bid made by the agent itself
        """""
        if not self._self_bid_history[-1][2]:
            if len(self._self_bid_history) <= 1:
                return 1
            return self._self_bid_history[-2][1]
        else:
            return self._self_bid_history[-1][1]

    def get_last_opponent_bid_utility(self):
        """""
        returns the utility of the last bid made by the agent itself
        """""
        if not self._self_bid_history[-1][2]:
            return self._self_bid_history[-1][1]
        else:
            return self._self_bid_history[-2][1]

    def rate_bid(self, bid: Bid, opponent_issue_percentage: Dict[str, Dict[Value, float]], opponent_issue_weights):
        """""
        Given a bid and the normalized _issue_count_dict this method estimates the utility of a Bid
        """""
        utility = 0
        for issue, value in bid.getIssueValues().items():
            utility += opponent_issue_percentage[issue][value] * opponent_issue_weights[issue]
        return utility
