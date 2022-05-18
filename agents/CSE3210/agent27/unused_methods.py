from math import *

# Here is some of the code we wrote during the development of the agent,
# which we did not use in the final version

"""
    Counts the number of occurrences of each issue in opponent's bid, and
    determines the best value for each issue
"""
def get_opponent_info(self):
    prev_bids = self.all_bids
    if len(prev_bids) < 2:
        return None

    # prev_bids.sort(key=lambda x: x[1])
    issues = self._last_received_bid.getIssues()

    demanded_best_offer = {}
    for issue in issues:
        issue_value_opponent = {}
        for i in range(len(prev_bids)):
            bid = prev_bids[i][0]
            val = bid.getValue(issue)
            if val in issue_value_opponent:
                issue_value_opponent[val] = issue_value_opponent[val] + 1
            else:
                issue_value_opponent[val] = 1

        sorted_dict = dict(sorted(issue_value_opponent.items(), key=lambda item: item[1]))
        opponent_val = list(sorted_dict.keys())[-1]
        demanded_best_offer[issue] = opponent_val

    return demanded_best_offer

"""
    Adds the values of issues found in opponent's offer in a global object.
"""
def get_opponent_preference(self):
    first_bid = self.all_bids[0][0]

    for issue in first_bid.getIssues():
        self.opponent_preferences.append((issue, first_bid.getValue(issue)))

""" 
    Sigmoid function

    Parameters
    ----------
    x: negotiation progress
"""

def sigmoid(self, x):
    return - 1 / (1 + exp(-5 * x + 5)) + 0.95

""" 
    Method for deciding whether an offer is good based on a sigmoid function 

    Parameters
    ----------
    bid: the offer that is received/ to be send    
"""

def _isGoodSigmoid(self, bid: Bid) -> bool:
    if bid is None:
        return False

    profile = self._profile.getProfile()
    progress = self._progress.get(time.time() * 1000)

    if float(profile.getUtility(bid)) > self.sigmoid(progress):
        return True
    return False

"""
    Finds the good bids from all bids.
"""
def find_all_good_bids(self):
    domain = self._profile.getProfile().getDomain()
    all_bids = AllBidsList(domain)

    for bid in all_bids:
        if self._isGood(bid):
            self.all_good_bids.append(bid)

"""
    Selects all favorable bids for the opponent based on issues that are not important to us, 
    but we consider them to be important fo the opponent.
"""
def get_all_suitable_bids(self):
    domain = self._profile.getProfile().getDomain()
    all_bids = AllBidsList(domain)

    opponent_desired_bid = self.get_opponent_info_good()
    not_important_issues = self.not_important_issues

    bids_with_utility = []

    for bid in all_bids:
        counter = 0
        if opponent_desired_bid is not None:
            for not_important_issue in not_important_issues:
                if bid.getIssueValues().get(not_important_issue) == opponent_desired_bid.get(not_important_issue):
                    counter += 1

        if (opponent_desired_bid is not None or counter == len(not_important_issues)) and self._isGood(bid):
            bids_with_utility.append((bid, self._profile.getProfile().getUtility(bid)))

    bids_with_utility = sorted(bids_with_utility, key=lambda item: -item[1])
    return bids_with_utility

"""
    Determines whether the opponent is repeating bids by checking 
    if the last 5 offers are the same.
"""
def is_opponent_repeating_bids(self):
    if len(self.all_bids) >= 5:
        for i in range(1, 5):
            if self.all_bids[-i] != self.all_bids[-i - 1]:
                return False
        return True
    return False

"""
    Searches for the smallest utility that is in the range between an utility that we think
    is appropriate and 1.
"""
def search_for_value(self, suggeseted_value_utility, issue):
    max_val = 1
    desired_value = ""
    utilities = self._profile.getProfile().getUtilities()
    all_values_for_issue = self._profile.getProfile().getDomain().getValues(issue)

    for v in all_values_for_issue:
        value_utility = utilities.get(issue).getUtility(v)
        if suggeseted_value_utility <= value_utility and value_utility <= max_val:
            desired_value = v
            max_val = value_utility
    return desired_value

