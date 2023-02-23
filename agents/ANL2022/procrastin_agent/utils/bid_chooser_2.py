import copy
from decimal import Decimal
from geniusweb.bidspace.AllBidsList import AllBidsList
from geniusweb.bidspace.BidsWithUtility import BidsWithUtility
from geniusweb.bidspace.Interval import Interval
from geniusweb.issuevalue.Bid import Bid
from geniusweb.issuevalue.Domain import Domain
from geniusweb.profile.utilityspace.LinearAdditiveUtilitySpace import (
    LinearAdditiveUtilitySpace,
)
from .opponent_model import OpponentModel
from .time_estimator import TimeEstimator

# Debug flags for testing
test_use_updates = True
test_use_safety = True

class BidChooser():
	def __init__(self, profile: LinearAdditiveUtilitySpace, opponent_model: OpponentModel, lowest_acceptable: float):
		self.profile = profile
		self.domain = profile.getDomain()
		self.opponent_model = opponent_model
		self.lowest_acceptable = lowest_acceptable
		self.lowest_with_bids = lowest_acceptable
		self.count = 0
		self.UPDATE_PERIOD = 100
		self.FLOAT_ERROR = 0.00001

		self.all_values = None
		self.opponent_best_values = None
		self.max_n_values = None
		bid_dict = {}
		for issue, valueset in self.profile.getUtilities().items():
			bid_dict[issue] = max(self.domain.getValues(issue), key = lambda v: valueset.getUtility(v))
		best_bid = Bid(bid_dict)
		self.bid_pool = [(best_bid, 1.0)]

		self.best_received_bid = None
		self.best_received_util = 0.0
		self.counting_down = False
		self.countdown = None

		self.initialize_global()
	
	def initialize_global(self):
		self_utilities = self.profile.getUtilities()

		# Generate all values (not needed)
		all_values = {issue: [v for v in valueset] for issue, valueset in self.domain.getIssuesValues().items()}
		for issue in self.domain.getIssues():
			values = self.domain.getValues(issue)
			valueset_utilities = self_utilities[issue]
			all_values[issue] = {v: float(valueset_utilities.getUtility(v)) for v in values}
			all_values[issue] = dict(sorted(all_values[issue].items(), key = lambda v: v[1], reverse = True))
		
		self.all_values = all_values

	def update_bid(self, bid: Bid):
		if not test_use_updates:
			return None
		if self.best_received_bid is None or self.best_received_util < float(self.profile.getUtility(bid)):
			self.best_received_bid = bid
			self.best_received_util = float(self.profile.getUtility(bid))
			old_lowest = self.lowest_with_bids
			self.lowest_with_bids = max(self.best_received_util, self.lowest_acceptable)
			if self.lowest_with_bids != old_lowest and self.bid_pool is not None:
				self._regenerate_bid_pool()

	def update_lowest_acceptable(self, lowest_acceptable: float):
		self.lowest_acceptable = lowest_acceptable
		old_lowest = self.lowest_acceptable
		self.lowest_with_bids = max(lowest_acceptable, self.best_received_util)
		if old_lowest != self.lowest_with_bids:
			self._regenerate_bid_pool()

	def choose_bid(self, offers_left: int, time: float):
		self._update_bid_pool()
		if not self.counting_down:
			if offers_left < len(self.bid_pool) * 2:
				self.counting_down = True
				self.countdown = min(len(self.bid_pool), offers_left)
			else:
				return self.bid_pool[-1][0]
		if self.counting_down:
			self.countdown -= 1
			if test_use_safety: # No matter how bad the time estimate is, don't concede faster than linear in bid order
				self.countdown = max(self.countdown, int((1.0 - time) * len(self.bid_pool)))
			if self.countdown > offers_left * 2:
				self.countdown = offers_left * 2
			if self.countdown < offers_left / 2: # TODO consider not reassigning value if offers_left is properly low (10 or fewer?)
				self.countdown = int(offers_left / 2)
			if self.countdown >= len(self.bid_pool):
				return self.bid_pool[-1][0]
			return self.bid_pool[max(self.countdown, 0)][0]

	def _update_bid_pool(self):
		self.count += 1
		if self.count % self.UPDATE_PERIOD == 0 or self.count == 1:
			self._regenerate_bid_pool()
	
	def _regenerate_bid_pool(self):
		self._construct_opponent_best_values()
		self._construct_max_n(n = 2)
		self._construct_bid_pool(lowest_acceptable = self.lowest_with_bids - self.FLOAT_ERROR)

	def _construct_opponent_best_values(self):
		self_utilities = self.profile.getUtilities()

		# Generate all values at least as good as opponnet's best
		# Should still be sorted
		self.opponent_best_values = {}
		for issue in self.all_values:
			opp_val_utils = self.opponent_model.get_value_utils(issue)
			self_val_utils = self_utilities[issue]
			opp_best_value = max(opp_val_utils, key = lambda v: opp_val_utils[v])
			opp_best_self_util = self.all_values[issue][opp_best_value]
			self.opponent_best_values[issue] = {v: self_util for v, self_util in self.all_values[issue].items() if self_util >= opp_best_self_util}
	
	def _construct_max_n(self, n: int):
		# Max n includes our best, their best, and up to n - 2 more
		# Current implementation uses our best n - 2.
		# TODO Consider using some other method such as their second / third best
		self.max_n_values = {}
		for issue, values in self.opponent_best_values.items():
			val_count = len(values)
			self.max_n_values[issue] = {}
			for i, (value, util) in enumerate(values.items()):
				if i < n - 1 or i == val_count - 1:
					self.max_n_values[issue][value] = util
		
	def _construct_bid_pool(self, lowest_acceptable: float):
		issue_weights = {issue: float(self.profile.getWeight(issue)) for issue in list(self.max_n_values.keys())}
		issue_weights_sorted = dict(sorted(issue_weights.items(), key = lambda i: i[1], reverse = True))
		issue_list = list(issue_weights_sorted.keys())
		new_bid_pool = []
		self._recur(self.max_n_values, issue_list, issue_weights_sorted, [], 1.0 - lowest_acceptable, new_bid_pool)
		new_bid_pool = sorted([(bid, float(self.profile.getUtility(bid))) for bid in new_bid_pool], key = lambda bid: bid[1])
		if self.best_received_util == self.lowest_with_bids:
			last_bid = new_bid_pool[-1][0]
			if last_bid != self.best_received_bid:
				new_bid_pool.insert(0, ((self.best_received_bid, float(self.profile.getUtility(self.best_received_bid)))))
		self.bid_pool = new_bid_pool

	def _recur(self, max_n_values: dict, issue_list: list, issue_weights: dict, bid: list, accumulated_loss: float, bids: list):
		issue = issue_list[len(bid)]
		last = len(bid) == len(issue_list) - 1
		weight = issue_weights[issue]
		for value, util in max_n_values[issue].items():
			new_accumulated_loss = accumulated_loss - weight * (1.0 - util)
			if new_accumulated_loss < 0.0:
				continue
			if not last:
				new_bid = copy.copy(bid)
				new_bid.append((issue, value))
				self._recur(max_n_values, issue_list, issue_weights, new_bid, new_accumulated_loss, bids)
			if last:
				last_bid = copy.copy(bid)
				last_bid.append((issue, value))
				bids.append(Bid(dict(last_bid)))

