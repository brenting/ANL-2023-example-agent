from collections import defaultdict

from geniusweb.issuevalue.Bid import Bid
from geniusweb.issuevalue.DiscreteValueSet import DiscreteValueSet
from geniusweb.issuevalue.Domain import Domain
from geniusweb.issuevalue.Value import Value


class OpponentModel:
    def __init__(self, domain: Domain):
        self.offers = []
        self.domain = domain

        self.issue_estimators = {
            i: IssueEstimator(v) for i, v in domain.getIssuesValues().items()
        }

    def update(self, bid: Bid, time: float):
        # keep track of all bids received
        self.offers.append(bid)

        # update all issue estimators with the value that is offered for that issue
        for issue_id, issue_estimator in self.issue_estimators.items():
            issue_estimator.update(bid.getValue(issue_id), time)

    def get_predicted_utility(self, bid: Bid):
        if len(self.offers) == 0 or bid is None:
            return 0

        # initiate
        total_issue_weight = 0.0
        value_utilities = []
        value_counts = []
        issue_weights = []

        for issue_id, issue_estimator in self.issue_estimators.items():
            # get the value that is set for this issue in the bid
            value: Value = bid.getValue(issue_id)

            # collect both the predicted weight for the issue and
            # predicted utility of the value within this issue
            value_utilities.append(issue_estimator.get_value_utility(value))
            value_counts.append(issue_estimator.value_trackers[value].count)
            issue_weights.append(issue_estimator.weight)

            total_issue_weight += issue_estimator.weight

        # normalise the issue weights such that the sum is 1.0
        if total_issue_weight == 0.0:
            issue_weights = [1 / len(issue_weights) for _ in issue_weights]
        else:
            issue_weights = [iw / total_issue_weight for iw in issue_weights]

        # calculate predicted utility by multiplying all value utilities with their issue weight
        predicted_utility = sum(
            [iw * vu for iw, vu in zip(issue_weights, value_utilities)]
        )
        prediction_uncertainty = sum(
            [iw * (2.0**(-max(vc, 1))) for iw, vc in zip(issue_weights, value_counts)]
        )

        return predicted_utility, prediction_uncertainty

    def get_issue_weights(self):
        total = sum(issue_estimator.weight for issue, issue_estimator in self.issue_estimators.items())
        issue_weights = {issue: issue_estimator.weight / total for issue, issue_estimator in self.issue_estimators.items()}
        return issue_weights

    def get_value_utils(self, issue: str):
        value_utils = {value: value_estimator.utility for value, value_estimator in self.issue_estimators[issue].value_trackers.items()}
        return value_utils


class IssueEstimator:
    def __init__(self, value_set: DiscreteValueSet):
        if not isinstance(value_set, DiscreteValueSet):
            raise TypeError(
                "This issue estimator only supports issues with discrete values"
            )

        self.bids_received = 0
        self.total_adjusted_value_count = 0
        self.max_value_count = 0
        self.max_adjusted_value_count = 0
        self.num_values = value_set.size()
        self.value_trackers = defaultdict(ValueEstimator)
        self.weight = 0

    def update(self, value: Value, time: float):
        self.bids_received += 1

        # get the value tracker of the value that is offered
        value_tracker = self.value_trackers[value]

        # register that this value was offered
        update_amount = value_tracker.update(time)
        self.total_adjusted_value_count += update_amount

        # update the count of the most common offered value
        self.max_value_count = max([value_tracker.count, self.max_value_count])
        self.max_adjusted_value_count = max([value_tracker.adjusted_count, self.max_adjusted_value_count])

        # update predicted issue weight
        # the intuition here is that if the values of the receiverd offers spread out over all
        # possible values, then this issue is likely not important to the opponent (weight == 0.0).
        # If all received offers proposed the same value for this issue,
        # then the predicted issue weight == 1.0
        equal_shares = self.bids_received / self.num_values
        adjusted_equal_shares = self.total_adjusted_value_count / self.num_values
        self.old_weight = (self.max_value_count - equal_shares) / (
            self.bids_received - equal_shares
        )
        self.weight = (self.max_adjusted_value_count - adjusted_equal_shares) / (
            self.total_adjusted_value_count - adjusted_equal_shares
        )

        # recalculate all value utilities
        for value_tracker in self.value_trackers.values():
            value_tracker.recalculate_utility(self.max_adjusted_value_count, self.weight)

    def get_value_utility(self, value: Value):
        if value in self.value_trackers:
            return self.value_trackers[value].utility

        return 0


class ValueEstimator:
    def __init__(self):
        self.count = 0
        self.adjusted_count = 0
        self.utility = 0

    def update(self, time):
        self.count += 1
        update_amount = (1.0 - 0.9 * time) / (self.count + 1.0)
        # update_amount = 1 # TODO Consider Removing
        self.adjusted_count += update_amount
        return update_amount

    def recalculate_utility(self, max_adjusted_value_count: int, weight: float):
        if weight < 1:
            mod_value_count = ((self.adjusted_count + 1) ** (1 - weight)) - 1
            mod_max_value_count = ((max_adjusted_value_count + 1) ** (1 - weight)) - 1

            self.utility = mod_value_count / mod_max_value_count
        else:
            self.utility = 1 if self.adjusted_count != 0 else 0
