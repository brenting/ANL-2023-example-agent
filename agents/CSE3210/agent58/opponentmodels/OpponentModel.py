from ..Constants import Constants


class OpponentModel:
    def __init__(self, domain):
        self._domain = domain
        self._freqs = {}
        for issue in self._domain.getIssues():
            self._freqs[issue] = {}

    # Update value frequency for new incoming bid
    def update_frequencies(self, bid):
        if bid is not None:
            for issue in self._domain.getIssues():
                value = bid.getValue(issue)
                if value in self._freqs[issue]:
                    self._freqs[issue][value] += 1
                else:
                    self._freqs[issue][value] = 1

    # returns normalized weights depending on importance of the issues
    # along with the largest value freq for each issue
    def _issue_weights(self):
        # For each issue we find the highest frequency
        max_freqs = {}
        max_f = 0
        for issue in self._domain.getIssues():
            max_freqs[issue] = 0
            for value in self._freqs[issue]:
                if max_freqs[issue] < self._freqs[issue][value]:
                    max_freqs[issue] = self._freqs[issue][value]
            if max_f < max_freqs[issue]:
                max_f = max_freqs[issue]
        weights = {}
        # normalize weights
        for issue in self._domain.getIssues():
            weights[issue] = max_freqs[issue] / max_f if max_f != 0 else 0
        return weights, max_freqs

    # returns the utility of our bid to opponent
    def utility(self, bid):
        u = 0
        weights, max_freqs = self._issue_weights()
        # utility is the sum of normalized value freq * issue weight
        for issue in self._domain.getIssues():
            value = bid.getValue(issue)
            if value in self._freqs[issue]:
                u += (self._freqs[issue][bid.getValue(issue)] / max_freqs[issue]) * weights[issue]

        u /= len(self._domain.getIssues())

        return u * Constants.opponent_model_offset
