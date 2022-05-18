from decimal import Decimal
from typing import Optional, Dict

from geniusweb.actions.Action import Action
from geniusweb.issuevalue.Bid import Bid
from geniusweb.issuevalue.Domain import Domain
from geniusweb.issuevalue.Value import Value
from geniusweb.opponentmodel.OpponentModel import OpponentModel
from geniusweb.profile.utilityspace.UtilitySpace import UtilitySpace
from geniusweb.progress.Progress import Progress
from geniusweb.references.Parameters import Parameters


class MyOpponentModel(UtilitySpace, OpponentModel):

    def __init__(self, domain: Domain, frequencies: [str, Dict[Value, int]], total: int, resBid: Optional[Bid]):
        """
        Initializes the opponent model with the given parameters.
        @param domain the domain of the negotiation
        @param frequencies the frequencies dictionary
        @param total the total amount of bids that have been recorded in the opponent model
        """
        self.domain = domain
        self.frequencies = frequencies
        self.total = total
        self.resBid = resBid

        # amount of unique bids, we will stop learning after this amount
        self.stop_learning_after = 30
        self.seen_bids = set()

    def With(self, domain: Domain, resBid: Optional[Bid]) -> "OpponentModel":
        return MyOpponentModel(domain=domain, frequencies={iss: {} for iss in domain.getIssues()}, total=0,
                               resBid=resBid)

    def WithAction(self, action: Action, progress: Progress) -> "OpponentModel":
        """
        Updates the opponent model with the given action.
        @param action most recent action to update the model with
        @param progress the progress of the negotiation expressed as a percentage of the amount of rounds
            that have passed
        @return The updated opponent model.
        """
        bid: Bid = action.getBid()
        if not bid:
            raise ValueError('No bid provided!')
        self.seen_bids.add(bid)
        if len(self.seen_bids) >= self.stop_learning_after:
            return self
        for issue in self.domain.getIssues():
            value = bid.getValue(issue)
            if value not in self.frequencies[issue]:
                self.frequencies[issue][value] = 0
            self.frequencies[issue][value] += 1
        self.total += 1
        return self

    @staticmethod
    def create():
        """
        Creates an empty opponent model without any of the parameters set

        @return an empty instance of MyOpponentModel
        """
        return MyOpponentModel(None, {}, 0, None)

    # Override
    def getUtility(self, bid: Bid) -> Decimal:
        """
        Estimates the opponents utility of a certain bid.
        @param bid the bid to estimate the utility for
        @return the utility as a decimal value between [0, 1]
        """
        if self.total == 0:
            return Decimal(1)

        issues = self.domain.getIssues()
        issue_weights = self._get_issue_weights(issues=issues)
        value_utilities = self._get_value_utilities_of_bid(issues=issues, bid=bid)

        total = Decimal(0)
        for issue in issue_weights:
            weight_of_value = value_utilities[issue]

            total += Decimal(issue_weights[issue] * weight_of_value)
        return total

    def _get_issue_weights(self, issues) -> dict:
        """
        Gets the estimated weight for each issue. It does this by first counting the amount
        of unique values we have been offered for each
        issue. Then it divides the total amount of bids by the amount of unique values this issue has.
        This number is then used to calculate the weight by dividing itself by the total amount of unique values.

        The logic behind this is that if the opponent only bids a few unique values for a issue, this issue
        probably has high importance to it since it is unwilling to compromise on this issue, whereas it is
        happy to concede on other issues.

        We have verified this method produces the expected outcome.

        @param issues all the issues to consider
        @return a dictionary with the estimated weights for each issue.
        """
        unique_bids_per_issue = dict()
        iwl = []
        issue_weights_dict = dict()
        total_unique_bids = 0
        for issue in issues:
            unique_bids = 0
            for value in self.frequencies[issue]:
                if self.frequencies[issue][value]:
                    unique_bids += 1
            unique_bids_per_issue[issue] = unique_bids
            total_unique_bids += unique_bids
        for issue in issues:
            score = total_unique_bids / unique_bids_per_issue[issue]
            iwl.append(score)
            issue_weights_dict[issue] = score
        total = sum(iwl)
        res = {k: (lambda x: (x / total))(v) for k, v in issue_weights_dict.items()}
        # debug purposes:
        # print('unique bids', unique_bids_per_issue)
        # print('frequencies', self.frequencies)
        # print('res', res)
        return res

    def _get_value_utilities_of_bid(self, issues, bid: Bid):
        """
        This method calculates the estimated utility for each value proposed in the bid.
        It does this by dividing the frequency of which the value has been offered by the total number of offers.
        You then get an utility in the range of [0, 1]

        We have verified this method produces the expected outcome.

        @param issues all the issues to consider
        @param bid the bid to calculate this for
        @return a dictionary with the utilities for each value in the bid
        """
        utilities = dict()
        for issue in issues:
            utilities[issue] = 0.5
            value = bid.getValue(issue)
            if issue in self.frequencies and value in self.frequencies[issue]:
                # print('Frequencies', self.frequencies[issue])
                # print('Value we are checking for', value)
                # print('Result', self.frequencies[issue][value] / self.total)
                utilities[issue] = self.frequencies[issue][value] / self.total
        return utilities

    def WithParameters(self, parameters: Parameters) -> "OpponentModel":
        """
        Does nothing, just returns itself.
        @return itself
        """
        return self
