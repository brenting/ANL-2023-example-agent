import logging
import math
import os.path
import random
import pickle
from time import time
from typing import cast
from collections import defaultdict
from typing import List
from geniusweb.profileconnection.ProfileInterface import ProfileInterface
from geniusweb.actions.Accept import Accept
from geniusweb.actions.Action import Action
from geniusweb.actions.Offer import Offer
from geniusweb.actions.PartyId import PartyId
from geniusweb.inform.ActionDone import ActionDone
from geniusweb.inform.Finished import Finished
from geniusweb.inform.Inform import Inform
from geniusweb.inform.Settings import Settings
from geniusweb.inform.YourTurn import YourTurn
from geniusweb.issuevalue.Bid import Bid
from geniusweb.bidspace.AllBidsList import AllBidsList
from geniusweb.party.Capabilities import Capabilities
from geniusweb.party.DefaultParty import DefaultParty
from geniusweb.utils import val
from geniusweb.issuevalue.Value import Value
from geniusweb.issuevalue import DiscreteValue
from geniusweb.issuevalue import NumberValue
from geniusweb.inform.Agreements import Agreements
from geniusweb.references.Parameters import Parameters
from geniusweb.profileconnection.ProfileConnectionFactory import (
    ProfileConnectionFactory,
)
from geniusweb.progress.ProgressRounds import ProgressRounds

from .utils.utils import get_ms_current_time
from .utils.pair import Pair
from .utils.persistent_data import PersistentData
from .utils.negotiation_data import NegotiationData


class SuperAgent(DefaultParty):
    """
    A Super party that places empty bids because it can't download the profile,
    and accepts the first incoming offer.
    """

    def __init__(self):
        super().__init__()
        self.getReporter().log(logging.INFO, "party is initialized")
        self._last_received_bid: Bid = None
        self._me = None
        self._profile_interface: ProfileInterface = None
        self._progress = None
        self._protocol = None
        self._parameters: Parameters = None
        self._utility_space = None
        self._domain = None
        self._settings: Settings = None

        self._best_offer_bid: Bid = None
        self._profile = None
        self._persistent_path: str = None
        self._persistent_data: PersistentData = None
        # NeogtiationData
        self._negotiation_data: NegotiationData = None
        self._data_paths_raw: List[str] = []
        # self._data_paths: List[str] = []
        self._negotiation_data_paths: List[str] = []
        self._opponent_name = None
        self._freq_map = defaultdict()
        self._avg_utility = 0.95
        self._std_utility = 0.15
        self._util_threshold = 0.95
        self._min_utility = 0.6
        self.default_alpha = 10.7
        self.alpha = self.default_alpha
        self.t_split = 40
        self.op_counter = [0] * self.t_split
        self.op_sum = [0.0] * self.t_split
        self.op_threshold = [0.0] * self.t_split
        self.t_phase = 0.2
        self.t_social_welfare = 0.997

        self._max_bid_space_iteration = 50000
        self._optimal_bid: Bid = None
        self._all_bid_list: AllBidsList = None
        self._sorted_bid_list: List = None
        self._len_sorted_bid_list: int = 0
        self._storage_dir: str = None

    def create_empty_negotiation_data(self, opponent_name):
        self._negotiation_data = NegotiationData(opponent_name=opponent_name)

    def initialize_negotiation_data(self, opponent_name):
        self._negotiation_data_paths = []
        data_path_raw = os.path.join(self._storage_dir, f"negotiation_data_{opponent_name}.log")
        self._negotiation_data_paths.append(data_path_raw)
        if self._negotiation_data is not None and os.path.exists(data_path_raw):
            # print("non-empty NegotiationData")
            with open(data_path_raw, "rb") as negotiation_data_file:
                self._negotiation_data: NegotiationData = pickle.load(negotiation_data_file)
        else:
            # print("empty NegotiationData")
            self.create_empty_negotiation_data(opponent_name=opponent_name)

    def initialize_persistent_data(self, opponent_name):
        self._persistent_path = os.path.join(self._storage_dir, f"persistent_data_{opponent_name}.log")
        if self._persistent_path is not None and os.path.exists(self._persistent_path):
            # json load
            # print("non-empty PersistentData")
            with open(self._persistent_path, "rb") as persistent_file:
                self._persistent_data: PersistentData = pickle.load(persistent_file)
            self._avg_utility = self._persistent_data.get_avg_utility()
            self._std_utility = self._persistent_data.get_std_utility()
        else:
            self._persistent_data: PersistentData = PersistentData()

    def first_better_then(self, utility):
        idx = None
        try:
            idx = next(len(self._sorted_bid_list) - 1 - x for x, val in enumerate(self._sorted_bid_list[-1::-1]) if
                               self.calc_utility(val) > utility)
        except StopIteration:
            pass
        finally:
            return idx

    def last_bids(self, good_bid: int):
        # this session's max utility got
        if self._progress.get(get_ms_current_time()) <= 0.97 and self.is_good(self._best_offer_bid):
            return self._best_offer_bid
        # all session's max utility got
        avg_max_util = self._persistent_data.get_avg_max_utility(self._opponent_name)
        if not avg_max_util:
            return self._best_offer_bid
        if self._progress.get(get_ms_current_time()) <= 0.99:
            idx = self.first_better_then(avg_max_util)
            if idx != None:
                self.getReporter().log(logging.INFO, "avg_max_util: {0}, bid_utility: {1}".format(avg_max_util,
                                                                                                  self._utility_space.getUtility(
                                                                                                      self._sorted_bid_list[
                                                                                                          idx])))
                if self.is_good(self._sorted_bid_list[idx]):
                    return self._sorted_bid_list[idx]

        # last try we give him the best possible suggestion we have
        if good_bid == 0:
            bid = self._optimal_bid
        else:
            bid = max(self._sorted_bid_list[0:good_bid], key=self.calc_op_value)

        self.getReporter().log(logging.INFO, "chosen bid utility: {}".format(self._utility_space.getUtility(bid)))
        return bid

    @classmethod
    def parse_opponent_name(cls, full_opponent_name):
        agent_index = full_opponent_name.rindex("_")
        if agent_index != -1:
            return full_opponent_name[:agent_index]
        return None

    def initialize_storage(self, opponent_name):
        if self._storage_dir is not None:
            self.initialize_persistent_data(opponent_name=opponent_name)
            self.initialize_negotiation_data(opponent_name=opponent_name)
        else:
            self.create_empty_negotiation_data(opponent_name=opponent_name)
            self._persistent_data: PersistentData = PersistentData()

    # Override
    def notifyChange(self, info: Inform):
        # self.getReporter().log(logging.INFO, "received info:" + str(info))
        if isinstance(info, Settings):
            # self.getReporter().log(logging.WARNING, "SETTINGS")
            settings: Settings = cast(Settings, info)
            self._settings = settings
            self._me: PartyId = settings.getID()
            self._progress = settings.getProgress()
            self._protocol = str(settings.getProtocol().getURI())
            self._parameters = settings.getParameters()
            if "storage_dir" in self._parameters.getParameters():
                self.getReporter().log(logging.INFO, "storage_dir is on parameters")
                self._storage_dir = self._parameters.get("storage_dir")

            try:
                self._profile_interface: ProfileInterface = ProfileConnectionFactory.create(
                    settings.getProfile().getURI(), self.getReporter()
                )
                self._profile = self._profile_interface.getProfile()
                self._domain = self._profile.getDomain()

                if self._freq_map is None:
                    self._freq_map = defaultdict()
                else:
                    self._freq_map.clear()

                issues = self._domain.getIssues()
                for issue in issues:
                    p = Pair()
                    vs = self._domain.getValues(issue)
                    if isinstance(vs.get(0), DiscreteValue.DiscreteValue):
                        p.value_type = 0
                    elif isinstance(vs.get(0), NumberValue.NumberValue):
                        p.value_type = 1
                    for v in vs:
                        vstr = self.value_to_str(v, p)
                        p.vlist[vstr] = 0
                    self._freq_map[issue] = p

                self._utility_space = self._profile_interface.getProfile()
                self._all_bid_list: AllBidsList = AllBidsList(domain=self._domain)
                self._sorted_bid_list = sorted(AllBidsList(domain=self._domain),
                                               key=self._utility_space.getUtility, reverse=True)
                self._len_sorted_bid_list = len(self._sorted_bid_list)
                # after sort of bid list the optimal bid is in the first element
                self._optimal_bid = self._sorted_bid_list[0]

            except Exception as e:
                print("error in settings:{}", e)
                self.getReporter().log(logging.WARNING, "Error in {}".format(str(e)))

        elif isinstance(info, ActionDone):
            # self.getReporter().log(logging.WARNING, "ActionDone")
            # TODO: initalizie with negotiaiondata
            action: Action = cast(ActionDone, info).getAction()
            if self._me is not None and self._me != action.getActor():
                opponent_name = self.parse_opponent_name(full_opponent_name=action.getActor().getName())
                if self._opponent_name is None and opponent_name is not None:
                    self.initialize_storage(opponent_name)
                    # which means index found
                    self._opponent_name = opponent_name
                    self._negotiation_data.set_opponent_name(self._opponent_name)

                    self.op_threshold = self._persistent_data.get_smooth_threshold_over_time(self._opponent_name
                                                                                             )
                    if self.op_threshold is not None:
                        for i in range(1, self.t_split):
                            self.op_threshold[i] = self.op_threshold[i] if self.op_threshold[i] > 0 else \
                                self.op_threshold[i - 1]
                    self.alpha = self._persistent_data.get_opponent_alpha(self._opponent_name)
                    self.alpha = self.alpha if self.alpha > 0.0 else self.default_alpha
                self.process_action(action)

        elif isinstance(info, YourTurn):
            # This is a super party
            # self.getReporter().log(logging.WARNING, "YourTurn")
            if isinstance(self._progress, ProgressRounds):
                self._progress = self._progress.advance()
            # self.initialize_storage(self._opponent_name)
            action = self._my_turn()
            val(self.getConnection()).send(action)

        elif isinstance(info, Finished):
            # TODO:: handle NEGOTIATIONDATA
            finished_info = cast(Finished, info)
            agreements: Agreements = finished_info.getAgreements()
            self.process_agreements(agreements)
            self.learn()
            if self._negotiation_data_paths is not None and len(
                    self._negotiation_data_paths) > 0 and self._negotiation_data is not None:
                for negotiation_path in self._negotiation_data_paths:
                    try:
                        with open(negotiation_path, "wb") as negotiation_file:
                            pickle.dump(self._negotiation_data, negotiation_file)
                    except Exception as e:
                        self.getReporter().log(logging.WARNING, "Error in {}".format(str(e)))
            self.terminate()
        else:
            self.getReporter().log(
                logging.WARNING, "Ignoring unknown info " + str(info)
            )

    # Override
    def getCapabilities(self) -> Capabilities:
        return Capabilities(
            set(["SAOP", "Learn"]),
            set(["geniusweb.profile.utilityspace.LinearAdditive"]),
        )

    # Override
    def getDescription(self) -> str:
        return "This is a party of ANL 2022. It can handle the Learn protocol and learns simple characteristics of the opponent."

    # Override
    def terminate(self):
        self.getReporter().log(logging.INFO, "party is terminating:")
        super().terminate()
        if self._profile_interface is not None:
            self._profile_interface.close()

    def value_to_str(self, v: Value, p: Pair) -> str:
        v_str = ""
        if p.value_type == 0:
            v_str = str(cast(DiscreteValue, v).getValue())
        elif p.value_type == 1:
            v_str = str(cast(NumberValue, v).getValue())

        if v_str == "":
            self.getReporter().log(logging.WARNING, "Warning: Value wasn't found")
        return v_str

    def process_action(self, action: Action):
        if isinstance(action, Offer):
            self._last_received_bid = cast(Offer, action).getBid()
            self.update_freq_map(self._last_received_bid)
            util_value = float(self._utility_space.getUtility(self._last_received_bid))
            self._negotiation_data.add_bid_util(util_value)

    def update_freq_map(self, bid: Bid):
        if bid is not None:
            issues = bid.getIssues()
            for issue in issues:
                p: Pair = self._freq_map[issue]
                v: Value = bid.getValue(issue)
                vs: str = self.value_to_str(v, p)
                p.vlist[vs] = p.vlist[vs] + 1

    def calc_op_value(self, bid: Bid):
        value: float = 0
        issues: set[str] = bid.getIssues()
        val_util: list[float] = [0] * len(issues)
        is_weight: list[float] = [0] * len(issues)
        k: int = 0
        for issue in issues:
            p: Pair = self._freq_map[issue]
            v: Value = bid.getValue(issue)
            vs: str = self.value_to_str(v=v, p=p)
            sum_of_values = 0
            max_value = 1
            for vString in p.vlist.keys():
                sum_of_values = sum_of_values + p.vlist.get(vString)
                max_value = max(max_value, p.vlist.get(vString))
            val_util[k] = float(p.vlist.get(vs)) / max_value
            mean = sum_of_values / len(p.vlist)
            for v_string in p.vlist.keys():
                is_weight[k] = is_weight[k] + math.pow(p.vlist.get(v_string) - mean, 2)
            is_weight[k] = 1 / math.sqrt((is_weight[k] + 0.1) / len(p.vlist))
            k = k + 1
        sum_of_weight = 0
        for k in range(len(issues)):
            value = value + val_util[k] * is_weight[k]
            sum_of_weight = sum_of_weight + is_weight[k]
        return value / sum_of_weight

    def is_op_good(self, bid: Bid):
        if bid is None:
            return False
        value = self.calc_op_value(bid=bid)
        index = int(
            ((self.t_split - 1) / (1 - self.t_phase) * (self._progress.get(get_ms_current_time()) - self.t_phase)))
        op_threshold = max(1 - 2 * self.op_threshold[index], 0.2) if self.op_threshold is not None else 0.6
        return value > op_threshold
        # index = (int)((t_split - 1) / (1 - t_phase) * (progress.get(System.currentTimeMillis()) - t_phase));

    def is_last_turn(self):
        return self._progress.get(time() * 1000) > 0.997

    def is_near_negotiation_end(self):
        return self._progress.get(time() * 1000) > self.t_phase

    def is_social_welfare_time(self):
        return self._progress.get(time() * 1000) > self.t_social_welfare

    def calc_utility(self, bid):
        # get utility from utility space
        return self._utility_space.getUtility(bid)

    def calc_social_welfare(self, bid: Bid):
        return 0.8 * float(self.calc_utility(bid)) + math.fabs(1 - 0.8) * float(self.calc_op_value(bid))

    def cmp_social_welfare(self, first_bid, second_bid):
        return self.calc_social_welfare(first_bid) >= self.calc_social_welfare(second_bid)

    def is_good(self, bid):
        if bid is None:
            return False
        max_value = 0.95 if self._optimal_bid is None else 0.95 * float(self.calc_utility(self._optimal_bid))
        avg_max_utility = self._persistent_data.get_avg_max_utility(self._opponent_name) \
            if self._persistent_data._known_opponent(self._opponent_name) \
            else self._avg_utility
        self._util_threshold = max_value - (
                max_value - 0.55 * self._avg_utility - 0.4 * avg_max_utility + 0.5 * pow(self._std_utility, 2)) * \
                               (math.exp(self.alpha * self._progress.get(get_ms_current_time())) - 1) / (math.exp(
            self.alpha) - 1)
        if self._util_threshold < self._min_utility:
            self._util_threshold = self._min_utility
        return float(self.calc_utility(bid)) >= self._util_threshold

    def first_is_good_idx(self):
        for i in range(len(self._sorted_bid_list)):
            if not self.is_good(self._sorted_bid_list[i]):
                return i
        return len(self._sorted_bid_list) - 1

    def on_negotiation_near_end(self):
        slice_idx = self.first_is_good_idx()
        end_slice = int(min(slice_idx + 0.005 * self._len_sorted_bid_list - 1, self._len_sorted_bid_list - 1))
        idx = random.randint(0, slice_idx)

        if self._progress.get(get_ms_current_time()) >= 0.95:
            bid = self.last_bids(idx)
            if self.calc_utility(bid) <= 0.5:
                bid = self._optimal_bid
            return bid
        # if self._progress.get(get_ms_current_time()) > 0.992 and self.is_good(self._best_offer_bid):
        #     return self._best_offer_bid
        return self._sorted_bid_list[idx]

    def on_negotiation_continues(self):
        bid: Bid = None

        slice_idx = self.first_is_good_idx()
        end_slice = int(min(slice_idx + 0.005 * self._len_sorted_bid_list - 1, self._len_sorted_bid_list - 1))
        for i in range(slice_idx, 0, -1):
            tmp_bid = self._sorted_bid_list[i]
            if tmp_bid == self._optimal_bid or self.is_op_good(tmp_bid):
                bid = tmp_bid
                break
        if self._progress.get(get_ms_current_time()) > 0.992 and self.is_good(self._best_offer_bid):
            bid = self._best_offer_bid
        if bid is None or not self.is_good(bid):
            idx = random.randint(0, slice_idx)
            bid = self._sorted_bid_list[idx]
        return bid

    def cmp_utility(self, first_bid, second_bid):
        # return 1 if first_bid with higher utility, 0 else
        return self._utility_space.getUtility(first_bid) > self._utility_space.getUtility(second_bid)

    def _find_bid(self):
        bid: Bid = None
        if self._best_offer_bid is None:
            self._best_offer_bid = self._last_received_bid
        elif self.cmp_utility(self._last_received_bid, self._best_offer_bid):
            self._best_offer_bid = self._last_received_bid
        # if self.is_social_welfare_time():
        #     self.on_negotiation_social_welfare()
        if self.is_near_negotiation_end():
            bid = self.on_negotiation_near_end()
        else:
            bid = self.on_negotiation_continues()

        action: Offer = Offer(self._me, bid)
        return action

    def _my_turn(self):
        # save average of the last avgSplit offers (only when frequency table is stabilized)
        if self._opponent_name is None:
            return Offer(self._me, self._optimal_bid)

        if self.is_near_negotiation_end():
            index = int(
                (self.t_split - 1) / (1 - self.t_phase) * (self._progress.get(get_ms_current_time()) - self.t_phase))
            self.op_sum[index] += self.calc_op_value(self._last_received_bid)
            self.op_counter[index] += 1
        if self.is_good(self._last_received_bid) or (self.is_last_turn() and self.calc_utility(self._last_received_bid)>=0.5):
            # if the last bid is good - accept it.
            action = Accept(self._me, self._last_received_bid)
        else:
            action = self._find_bid()
        return action

    def learn(self):
        self.getReporter().log(logging.INFO, "party is learning")
        # probably have to shift to self._negotiation_data_paths
        for path in self._negotiation_data_paths:
            try:
                with open(path, "rb") as f:
                    nego_data = pickle.load(f)
                self._persistent_data.update(nego_data)
            except Exception as e:
                print("error in learn function - persistent data update, error:{}", str(e))

        try:
            with open(self._persistent_path, "wb") as pers_file:
                pickle.dump(self._persistent_data, pers_file)
        except Exception as e:
            print("error in persistent path dump:{}", str(e))

    def process_agreements(self, agreements: Agreements):
        # Check if we reached an agreement (walking away or passing the deadline
        # results in no agreement)
        self.getReporter().log(logging.INFO, "Length of agreements: {} :{}".format(len(agreements.getMap().items()),
                                                                                   agreements.getMap()))
        if len(agreements.getMap().items()) > 0:
            # Get the bid that is agreed upon and add it's value to our negotiation data
            agreement: Bid = agreements.getMap().values().__iter__().__next__()
            self._negotiation_data.add_agreement_util(float(self.calc_utility(agreement)))
            self._negotiation_data.set_opponent_util(self.calc_op_value(agreement))
            self.getReporter().log(logging.INFO, "Agreement in time: {} percent".format(self._progress.get(get_ms_current_time())))
            self.getReporter().log(logging.INFO, "MY OWN THRESHOLD: {}".format(self._util_threshold))
            self.getReporter().log(logging.INFO, "MY OWN UTIL:{}".format(self.calc_utility(agreement)))
            self.getReporter().log(logging.INFO, "EXP OPPONENT UTIL:{}".format(self.calc_op_value(agreement)))
        else:
            if self._best_offer_bid is not None:
                self._negotiation_data.add_agreement_util(float(self.calc_utility(self._best_offer_bid)))
            self.getReporter().log(logging.INFO,
                                   "!!!!!!!!!!!!!! NO AGREEMENT !!!!!!!!!!!!!!! /// MY THRESHOLD: {}".format(
                                       self._util_threshold))

        self.getReporter().log(logging.INFO, "TIME OF AGREEMENT: {}".format(self._progress.get(get_ms_current_time())))
        # update the opponent offers map, regardless of achieving agreement or not
        try:
            self._negotiation_data.update_opponent_offers(self.op_sum, self.op_counter)
        except Exception as e:
            self.getReporter().log(logging.INFO, "Error in process_agreements,{}".format(str(e)))
