import json
import logging
import math
import os.path
import random
from decimal import Decimal
from random import randint
from time import time
from typing import cast
from typing import final

import geniusweb.actions.LearningDone
from geniusweb.actions.Accept import Accept
from geniusweb.actions.Action import Action
from geniusweb.actions.Offer import Offer
from geniusweb.actions.PartyId import PartyId
from geniusweb.bidspace.AllBidsList import AllBidsList
from geniusweb.inform.ActionDone import ActionDone
from geniusweb.inform.Finished import Finished
from geniusweb.inform.Inform import Inform
from geniusweb.inform.Settings import Settings
from geniusweb.inform.YourTurn import YourTurn
from geniusweb.issuevalue import DiscreteValue, NumberValue
from geniusweb.issuevalue.Bid import Bid
from geniusweb.issuevalue.Domain import Domain
from geniusweb.party.Capabilities import Capabilities
from geniusweb.party.DefaultParty import DefaultParty
from geniusweb.profile.utilityspace import UtilitySpace
from geniusweb.bidspace.AllBidsList import AllBidsList
from geniusweb.profile.utilityspace.LinearAdditiveUtilitySpace import (
    LinearAdditiveUtilitySpace,
)
from geniusweb.profileconnection.ProfileConnectionFactory import (
    ProfileConnectionFactory,
)
from geniusweb.profileconnection.ProfileInterface import (
    ProfileInterface
)
from geniusweb.progress.ProgressRounds import ProgressRounds
from geniusweb.progress.ProgressTime import ProgressTime
from geniusweb.references.Parameters import Parameters
from tudelft_utilities_logging.ReportToLogger import ReportToLogger

from agents.template_agent.utils.opponent_model import OpponentModel


class SmartAgent(DefaultParty):
    def __init__(self):
        super().__init__()

        self.all_bid_list = None
        self.logger: ReportToLogger = self.getReporter()

        self.domain: Domain = None
        self.parameters: Parameters = None
        self.profile: LinearAdditiveUtilitySpace = None
        self.profileInt: ProfileInterface = None
        self.progress: ProgressTime = None
        self.me: PartyId = None
        self.random: final(random) = random.Random()
        self.protocol = ""
        self.opponent_name: str = None
        self.settings: Settings = None
        self.storage_dir: str = None

        self.time_split = 40
        self.time_phase = 0.2
        self.new_weight = 0.3
        self.smooth_width = 3
        self.opponent_decrease = 0.65
        self.default_alpha = 10.7
        self.alpha = self.default_alpha

        self.opponent_avg_utility = 0.0
        self.opponent_negotiations = 0
        self.opponent_avg_max_utility = {}
        self.opponent_encounters = {}

        self.std_utility = 0.0
        self.negotiation_results = []
        self.avg_opponent_utility = {}
        self.opponent_alpha = {}
        self.opponent_sum = [0.0] * 5000
        self.opponent_counter = [0.0] * 5000

        self.persistent_state = {"opponent_alpha": self.default_alpha, "avg_max_utility": 0.0}
        self.negotiation_data = {"aggreement_util": 0.0, "max_received_util": 0.0, "opponent_name": "", "opponent_util": 0.0,
                                "opponent_util_by_time": [0.0] * self.time_split}
        self.opponent_utility_by_time = self.negotiation_data["opponent_util_by_time"]
        self.need_to_read_persistent_data = True
        self.freqMap = {}
        self.MAX_SEARCHABLE_BIDSPACE = 50000
        self.utilitySpace: UtilitySpace = None
        self.all_bid_list: AllBidsList
        self.optimalBid: Bid = None
        self.bestOfferedBid: Bid = None
        self.utilThreshold = None
        self.opThreshold = None
        self.last_received_bid: Bid = None
        self.opponent_model: OpponentModel = None
        self.logger.log(logging.INFO, "party is initialized")

    def notifyChange(self, data: Inform):
        """MUST BE IMPLEMENTED
        This is the entry point of all interaction with your agent after is has been initialised.
        How to handle the received data is based on its class type.

        Args:
            info (Inform): Contains either a request for action or information.
        """

        # a Settings message is the first message that will be send to your
        # agent containing all the information about the negotiation session.
        try:
            if isinstance(data, Settings):
                # data is an object that is passed at the start of the negotiation
                self.settings = cast(Settings, data)
                # ID of my agent
                self.me = self.settings.getID()

                # progress towards the deadline has to be tracked manually through the use of the Progress object
                self.progress = self.settings.getProgress()

                self.protocol = self.settings.getProtocol().getURI().getPath()
                self.parameters = self.settings.getParameters()
                self.storage_dir = self.parameters.get("storage_dir")

                # TODO: Add persistance
                # the profile contains the preferences of the agent over the domain
                profile_connection = ProfileConnectionFactory.create(
                    data.getProfile().getURI(), self.getReporter()
                )
                self.profile = profile_connection.getProfile()
                self.domain = self.profile.getDomain()

                if str(self.settings.getProtocol().getURI()) == "Learn":
                    self.learn()
                    self.getConnection().send(geniusweb.actions.LearningDone.LearningDone)
                else:
                    # This is the negotiation step
                    try:
                        self.profileInt = ProfileConnectionFactory.create(self.settings.getProfile().getURI(),
                                                                          self.getReporter())
                        domain = self.profileInt.getProfile().getDomain()

                        if self.freqMap != {}:
                            self.freqMap.clear()
                        issues = domain.getIssues()
                        for s in issues:
                            pair = ({}, {})
                            vlist = pair[1]
                            vs = domain.getValues(s)
                            if isinstance(vs.get(0), DiscreteValue.DiscreteValue.__class__):
                                pair.type = 0
                            elif isinstance(vs.get(0), NumberValue.NumberValue.__class__):
                                pair.type = 1
                            for v in vs:
                                vlist[str(v)] = 0
                            self.freqMap[s] = pair
                        self.utilitySpace: UtilitySpace.UtilitySpace = self.profileInt.getProfile()
                        self.all_bid_list = AllBidsList(domain)

                        bids_zise = self.all_bid_list.size()
                        if bids_zise < self.MAX_SEARCHABLE_BIDSPACE:
                            r = -1
                        elif bids_zise == self.MAX_SEARCHABLE_BIDSPACE:
                            r = 0
                        else:
                            r = 1
                        if r == 0 or r == -1:
                            mx_util = 0
                            bidspace_size = self.all_bid_list.size()
                            for i in range(0, bidspace_size, 1):
                                b: Bid = self.all_bid_list.get(i)
                                candidate = self.utilitySpace.getUtility(b)
                                r = candidate.compare(mx_util)
                                if r == 1:
                                     mx_util = candidate
                                     self.optimalBid = b
                        else:
                            # Searching for best bid in random subspace
                            mx_util = 0
                            for attempt in range(0,self.MAX_SEARCHABLE_BIDSPACE,1):
                                irandom = random.random(self.all_bid_list.size())
                                b = self.all_bid_list.get(irandom)
                                candidate = self.utilitySpace.getUtility(b)
                                r = candidate.compare(mx_util)
                                if r == 1:
                                    mx_util = candidate
                                    self.optimalBid = b
                    except:
                        raise Exception("Illegal state exception")
                profile_connection.close()
            # ActionDone informs you of an action (an offer or an accept)
            # that is performed by one of the agents (including yourself).
            elif isinstance(data, ActionDone):
                action = cast(ActionDone, data).getAction()
                actor = action.getActor()
                # ignore action if it is our action
                if actor != self.me:
                    # obtain the name of the opponent, cutting of the position ID.
                    self.opponent_name = str(actor).rsplit("_", 1)[0]
                    if self.need_to_read_persistent_data:
                        self.negotiation_data = self.read_persistent_negotiation_data()
                        self.need_to_read_persistent_data = False
                    self.negotiation_data["opponent_name"] = self.opponent_name
                    self.opThreshold = self.getSmoothThresholdOverTime(self.opponent_name)
                    if self.opThreshold is not None:
                        for i in range(1, self.time_split, 1):
                            if self.opThreshold[i] < 0:
                                self.opThreshold[i] = self.opThreshold[i - 1]
                    self.alpha = self.persistent_state["opponent_alpha"]
                    if self.alpha < 0.0:
                        self.alpha = self.default_alpha
                    self.update_negotiation_data()

                    # process action done by opponent
                    self.opponent_action(action)

            # YourTurn notifies you that it is your turn to act
            elif isinstance(data, YourTurn):
                if isinstance(self.progress, ProgressRounds):
                    self.progress = cast(ProgressRounds, self.progress).advance()
                self.my_turn()
                # Finished will be send if the negotiation has ended (through agreement or deadline)
            elif isinstance(data, Finished):
                self.negotiation_data["aggreement_util"] = float(self.utilitySpace.getUtility(self.last_received_bid))
                self.negotiation_data["opponent_util"] = self.calc_opponnets_value(self.last_received_bid)
                self.update_opponents_offers(self.opponent_sum, self.opponent_counter)
                self.save_data()
                # terminate the agent MUST BE CALLED
                self.logger.log(logging.INFO, "party is terminating:")
                super().terminate()
            else:
                self.logger.log(logging.WARNING, "Ignoring unknown info " + str(data))
        except:
            raise Exception("Illegal state exception")

    def getCapabilities(self) -> Capabilities:
        """MUST BE IMPLEMENTED
        Method to indicate to the protocol what the capabilities of this agent are.
        Leave it as is for the ANL 2022 competition

        Returns:
            Capabilities: Capabilities representation class
        """
        return Capabilities(
            set(["SAOP", "Learn"]),
            set(["geniusweb.profile.utilityspace.LinearAdditive"]),
        )

    def send_action(self, action: Action):
        """Sends an action to the opponent(s)

        Args:
            action (Action): action of this agent
        """
        self.getConnection().send(action)

    # give a description of your agent
    def getDescription(self) -> str:
        """MUST BE IMPLEMENTED
        Returns a description of your agent. 1 or 2 sentences.

        Returns:
            str: Agent description
        """
        return "Smart agent for the ANL 2022 competition"

    def update_frequency_map(self, bid):
        if bid is not None:
            issues = bid.getIssues()
            for s in issues:
                p = self.freqMap.get(s)
                v = bid.getValue(s)
                vList = p[1]
                vList[str(v)] += 1

    def opponent_action(self, action):
        """Process an action that was received from the opponent.

        Args:
            action (Action): action of opponent
        """
        # if it is an offer, set the last received bid
        if isinstance(action, Offer):
            # create opponent model if it was not yet initialised
            if self.opponent_model is None:
                self.opponent_model = OpponentModel(self.domain)

            bid = cast(Offer, action).getBid()
            # update opponent model with bid
            self.opponent_model.update(bid)
            self.update_negotiation_data()
            # set bid as last received
            self.last_received_bid = bid
            self.update_frequency_map(self.last_received_bid)
            utilVal = self.utilitySpace.getUtility(bid)
            self.negotiation_data["max_received_util"] = float(utilVal)
        if isinstance(action, Accept):
            self.last_received_bid = self.optimalBid
    def my_turn(self):
        """This method is called when it is our turn. It should decide upon an action
        to perform and send this action to the opponent.
        """
        if self.is_near_negotiation_end() > 0:
            index = int((self.time_split - 1) / (1 - self.time_phase) * (self.progress.get(int(time() * 1000)) - self.time_phase))
            if self.opponent_sum[index]:
                self.opponent_sum[index] = self.calc_opponnets_value(self.last_received_bid)
            else:
                self.opponent_sum[index] += self.calc_opponnets_value(self.last_received_bid)
            self.opponent_counter[index] += 1
        # check if the last received offer is good enough
        if self.accept_condition(self.last_received_bid):
            # if so, accept the offer
            action = Accept(self.me, self.last_received_bid)
        else:
            # if not, find a bid to propose as counter offer
            bid: Bid = None

            if self.bestOfferedBid is None:
                self.bestOfferedBid = self.last_received_bid
            elif self.utilitySpace.getUtility(self.last_received_bid) > self.utilitySpace.getUtility(
                    self.bestOfferedBid):
                self.bestOfferedBid = self.last_received_bid
            if self.is_near_negotiation_end() == 0:
                for attempt in range(0, 1000, 1):
                    if not self.accept_condition(bid):
                        i = random.randint(0, self.all_bid_list.size())
                        bid = self.all_bid_list.get(i)
                    if self.accept_condition(bid):
                        bid = bid
                    else:
                        bid = self.optimalBid

            else:
                for attempt in range(0, 1000, 1):
                    if bid != self.optimalBid and not self.accept_condition(bid) and not self.is_opponents_proposal_is_good(bid):
                        i = random.randint(0, self.all_bid_list.size())
                        bid = self.all_bid_list.get(i)
                    if self.progress.get(int(time()) * 1000) > 0.99 and self.accept_condition(self.bestOfferedBid):
                        bid = self.bestOfferedBid
                    if not self.accept_condition(bid):
                        bid = self.optimalBid
            action = Offer(self.me, bid)

        # send the action
        self.send_action(action)

    def read_persistent_negotiation_data(self):
        if os.path.exists(f"{self.storage_dir}/{self.opponent_name}"):
            with open(f"{self.storage_dir}/{self.opponent_name}", "r") as f:
                data = json.load(f)
                return data
        else:
            return {"opponent_alpha": self.default_alpha, "aggreement_util": 0.0, "max_received_util": 0.0,
                    "opponent_name": self.opponent_name,
                    "opponent_util": 0.0,
                    "opponent_util_by_time": [0.0] * self.time_split}

    def save_data(self):
        """This method is called after the negotiation is finished. It can be used to store data
        for learning capabilities. Note that no extensive calculations can be done within this method.
        Taking too much time might result in your agent being killed, so use it for storage only.
        """
        with open(f"{self.storage_dir}/{self.opponent_name}", "w") as f:
            f.write(json.dumps(self.negotiation_data))

    def is_near_negotiation_end(self):
        prog = self.progress.get(time() * 1000)
        if prog < self.time_phase:
            return 0
        else:
            return 1

    def calc_opponnets_value(self, bid: Bid):
        if not bid:
             return 0
        # # own_utility = self.profile.getProfile().getUtility(bid)
        # opponent_utility = self.opponent_model.get_predicted_utility(bid)  # .getUtility(bid)
        # return opponent_utility
        value = 0
        issues = bid.getIssues()
        valUtil = [0.0]*len(issues)
        isWeght = [0.0]*len(issues)
        k = 0
        for s in issues:
            p = self.freqMap.get(s)
            v = bid.getValue(s)
            sumOfValues = 0
            maxValue = 1
            for vString in p[1].keys():
                sumOfValues += p[1].get(vString)
                maxValue = max(maxValue, p[1].get(vString))
            valUtil[k] = float(p[1].get(vString)/maxValue)
            mean = float(sumOfValues/len(p[1]))
            for vString in p[1].keys():
                isWeght[k] += math.pow(p[1].get(vString) - mean, 2)
            isWeght[k] = 1.0/(math.sqrt(isWeght[k] + 0.1)/len(p[1]))
            k += 1
        sumOfwght = 0
        for k in range(0, len(issues)):
            value += valUtil[k] * isWeght[k]
            sumOfwght += isWeght[k]
        return value/sumOfwght

    def is_opponents_proposal_is_good(self, bid: Bid):
        if bid == None:
            return 0
        value = self.calc_opponnets_value(bid)
        index = int(((self.time_split - 1) / (1 - self.time_phase) * (self.progress.get(time() * 1000) - self.time_phase)))
        if self.opThreshold != None:
            self.opThreshold = max(1 - 2 * self.opThreshold[index], 0.2)
        else:
            self.opThreshold = 0.6
        return value > self.opThreshold

    ###########################################################################################
    ################################## Example methods below ##################################
    ###########################################################################################

    def accept_condition(self, bid: Bid) -> bool:
        if bid is None or self.opponent_name is None:
            return False
        avg_max_utility = self.avg_opponent_utility[self.opponent_name]
        if self.optimalBid is not None:
            maxValue = 0.95 * float(self.utilitySpace.getUtility(self.optimalBid))
        else:
            maxValue = 0.95
        if self.isKnownOpponent(self.opponent_name):
            avg_max_utility = self.avg_opponent_utility[self.opponent_name]
        if self.alpha != 0:
            self.utilThreshold = maxValue - (
                    maxValue - 0.6 * self.opponent_avg_utility - 0.4 * avg_max_utility + pow(self.std_utility, 2)) * (
                                             math.exp(self.alpha * self.progress.get(time() * 1000) - 1) - 1) / (
                                             math.exp(self.alpha) - 1)
        return self.utilitySpace.getUtility(bid) >= self.utilThreshold

    def find_bid(self) -> Bid:
        # compose a list of all possible bids
        domain = self.profile.getDomain()
        all_bids = AllBidsList(domain)

        best_bid_score = 0.0
        best_bid = None

        # take 500 attempts to find a bid according to a heuristic score
        for _ in range(500):
            bid = all_bids.get(randint(0, all_bids.size() - 1))
            bid_score = self.score_bid(bid)
            if bid_score > best_bid_score:
                best_bid_score, best_bid = bid_score, bid

        return best_bid

    def score_bid(self, bid: Bid, alpha: float = 0.95, eps: float = 0.1) -> float:
        """Calculate heuristic score for a bid

        Args:
            bid (Bid): Bid to score
            alpha (float, optional): Trade-off factor between self interested and
                altruistic behaviour. Defaults to 0.95.
            eps (float, optional): Time pressure factor, balances between conceding
                and Boulware behaviour over time. Defaults to 0.1.

        Returns:
            float: score
        """
        progress = self.progress.get(time() * 1000)

        our_utility = float(self.profile.getUtility(bid))

        time_pressure = 1.0 - progress ** (1 / eps)
        score = alpha * time_pressure * our_utility

        if self.opponent_model is not None:
            opponent_utility = self.opponent_model.get_predicted_utility(bid)
            opponent_score = (1.0 - alpha * time_pressure) * opponent_utility
            score += opponent_score

        return score

    def learn(self):
        # not called...
        return "ok"

    def isKnownOpponent(self, opponent_name):
        return self.opponent_encounters.get(opponent_name, 0)

    def getSmoothThresholdOverTime(self, opponent_name):
        if not self.isKnownOpponent(opponent_name):
            return None
        opponentTimeUtil = self.negotiation_data["opponent_util_by_time"]
        smoothedTimeUtil = [0.0] * self.time_split

        for i in range(0, self.time_split, 1):
            for j in range(max(i - self.smooth_width, 0), min(i + self.smooth_width + 1, self.time_split), 1):
                smoothedTimeUtil[i] += opponentTimeUtil[j]
            smoothedTimeUtil[i] /= (min(i + self.smooth_width + 1, self.time_split) - max(i - self.smooth_width, 0))
        return smoothedTimeUtil

    def calculate_alpha(self, opponent_name):
        alphaArray = self.getSmoothThresholdOverTime(opponent_name)
        if alphaArray == None:
            return self.default_alpha
        for maxIndex in range(0, self.time_split, 1):
            if alphaArray[maxIndex] > 0.2:
                break
        maxValue = alphaArray[0]
        minValue = alphaArray[max(maxIndex - self.smooth_width - 1, 0)]

        if maxValue - minValue < 0.1:
            return self.default_alpha
        for t in range(0, maxIndex, 1):
            if alphaArray[t] > (maxValue - self.opponent_decrease * (maxValue - minValue)):
                break
        calibratedPolynom = {572.83, -1186.7, 899.29, -284.68, 32.911}
        alpha = calibratedPolynom[0]

        # lowers utility at 85% of the time why 85% ???
        tTime = self.time_phase + (1 - self.time_phase) * (
                maxIndex * (float(t) / self.time_split) + (self.time_split - maxIndex) * 0.85) / self.time_split
        for i in range(1, len(calibratedPolynom), 1):
            alpha = alpha * tTime + calibratedPolynom[i]

        return alpha

    def update_opponents_offers(self, op_sum, op_counts):
        for i in range(0, self.time_split):
            if op_counts[i] > 0:
                self.negotiation_data["opponent_util_by_time"][i] = op_sum[i]/op_counts[i]
            else:
                self.negotiation_data["opponent_util_by_time"][i] = 0

    def update_negotiation_data(self):
        if self.negotiation_data.get("aggreement_util") > 0:
            newUtil = self.negotiation_data.get("aggreement_util")
        else:
            newUtil = self.opponent_avg_utility - 1.1 * math.pow(self.std_utility, 2)
        self.opponent_avg_utility = (self.opponent_avg_utility * self.opponent_negotiations + newUtil) / (
                self.opponent_negotiations + 1)
        self.opponent_negotiations += 1
        self.avg_opponent_utility[self.opponent_name] = self.opponent_avg_utility
        self.negotiation_results.append(self.negotiation_data["aggreement_util"])
        self.std_utility = 0.0
        for util in self.negotiation_results:
            self.std_utility += math.pow(util - self.opponent_avg_utility, 2)
        self.std_utility = math.sqrt(self.std_utility / self.opponent_negotiations)

        opponent_name = self.negotiation_data["opponent_name"]

        if opponent_name != "":
            if self.opponent_encounters.get(opponent_name):
                encounters = self.opponent_encounters.get(opponent_name)
            else:
                encounters = 0
            self.opponent_encounters[opponent_name] = encounters + 1

            if self.opponent_avg_max_utility.get(opponent_name):
                avgUtil = self.opponent_avg_max_utility[opponent_name]
            else:
                avgUtil = 0.0
            calculated_opponent_avg_max_utility = (float(avgUtil * encounters) + float(
                self.negotiation_data["max_received_util"])) / (
                                                          encounters + 1)
            self.opponent_avg_max_utility[opponent_name] = calculated_opponent_avg_max_utility

            if self.avg_opponent_utility[opponent_name]:
                avgOpUtil = self.avg_opponent_utility[opponent_name]
            else:
                avgOpUtil = 0.0
            calculated_opponent_avg_utility = (float(avgOpUtil * encounters) + float(
                self.negotiation_data["opponent_util"])) / (
                                                      encounters + 1)
            self.avg_opponent_utility[opponent_name] = calculated_opponent_avg_utility
            if self.opponent_utility_by_time:
                opponentTimeUtility = self.opponent_utility_by_time
            else:
                opponentTimeUtility = [0.0] * self.time_split

            newUtilData = self.negotiation_data.get("opponent_util_by_time")
            if opponentTimeUtility[0] > 0.0:
                ratio = ((1 - self.new_weight) * opponentTimeUtility[0] + self.new_weight * newUtilData[0] /
                         opponentTimeUtility[0])
            else:
                ratio = 1
            for i in range(0, self.time_split, 1):
                if newUtilData[i] > 0:
                    valueUtilData = (
                            (1 - self.new_weight) * opponentTimeUtility[i] + self.new_weight * newUtilData[i])
                    opponentTimeUtility[i] = valueUtilData
                else:
                    opponentTimeUtility[i] *= ratio
            self.negotiation_data["opponent_util_by_time"] = opponentTimeUtility
            self.opponent_alpha[opponent_name] = self.calculate_alpha(opponent_name)

