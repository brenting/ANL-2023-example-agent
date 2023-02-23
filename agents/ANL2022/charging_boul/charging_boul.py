from .extended_util_space import ExtendedUtilSpace
from .utils.opponent_model import OpponentModel
from decimal import Decimal
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
from geniusweb.issuevalue.Domain import Domain
from geniusweb.party.Capabilities import Capabilities
from geniusweb.party.DefaultParty import DefaultParty
from geniusweb.profile.utilityspace.LinearAdditive import LinearAdditive
from geniusweb.profileconnection.ProfileConnectionFactory import ProfileConnectionFactory
from geniusweb.profileconnection.ProfileInterface import ProfileInterface
from geniusweb.progress.Progress import Progress
from geniusweb.references.Parameters import Parameters
from json import dump, load
from random import randint
from statistics import mean
from time import time as clock
from tudelft.utilities.immutablelist.ImmutableList import ImmutableList
from tudelft_utilities_logging.Reporter import Reporter
import logging


class ChargingBoul(DefaultParty):
    def __init__(self, reporter: Reporter = None):
        super().__init__(reporter)
        self.best_received_bid: Bid = None
        self.best_received_util: Decimal = Decimal(0)
        self.domain: Domain = None
        self.e: float = 0.1
        self.extended_space: ExtendedUtilSpace = None
        self.filepath: str = None
        self.final_rounds: int = 90
        self.last_received_bid: Bid = None
        self.last_received_util: Decimal = None
        self.max_util = Decimal(1)
        self.me: PartyId = None
        self.min_util = Decimal(0.5)
        self.opponent_model: OpponentModel = None
        self.opponent_strategy: str = None
        self.other: str = None
        self.parameters: Parameters = None
        self.profile_int: ProfileInterface = None
        self.progress: Progress = None
        self.received_bids: list = []
        self.received_utils: list = []
        self.settings: Settings = None
        self.storage_dir: str = None
        self.summary: dict = None
        self.util_space: LinearAdditive = None
        self.getReporter().log(logging.INFO, "party is initialized")

    def notifyChange(self, info: Inform):
        """MUST BE IMPLEMENTED
        This is the entry point of all interaction with your agent after is has been initialised.
        How to handle the received data is based on its class type.

        Args:
            info (Inform): Contains either a request for action or information.
        """
        try:
            if isinstance(info, Settings):
                self.settings = info
                self.me = self.settings.getID()
                self.parameters = self.settings.getParameters()
                self.profile_int = ProfileConnectionFactory.create(
                    self.settings.getProfile().getURI(), self.getReporter()
                )
                self.progress = self.settings.getProgress()
                self.storage_dir = self.parameters.get("storage_dir")
                self.util_space = self.profile_int.getProfile()
                self.domain = self.util_space.getDomain()
                self.extended_space = ExtendedUtilSpace(self.util_space)
                self.detect_strategy()
            elif isinstance(info, ActionDone):
                other_act: Action = info.getAction()
                actor = other_act.getActor()
                if actor != self.me:
                    self.other = str(actor).rsplit("_", 1)[0]
                    self.filepath = f"{self.storage_dir}/{self.other}.json"
                if isinstance(other_act, Offer):
                    # create opponent model if it was not yet initialised
                    if self.opponent_model is None:
                        self.opponent_model = OpponentModel(self.domain)
                    self.last_received_bid = other_act.getBid()
                    self.last_received_util = self.util_space.getUtility(self.last_received_bid)
                    # update opponent model with bid
                    self.opponent_model.update(self.last_received_bid)
            elif isinstance(info, YourTurn):
                self.my_turn()
            elif isinstance(info, Finished):
                self.getReporter().log(logging.INFO, "Final outcome:" + str(info))
                self.terminate()
                # stop this party and free resources.
        except Exception as ex:
            self.getReporter().log(logging.CRITICAL, "Failed to handle info", ex)

    def getCapabilities(self) -> Capabilities:
        """MUST BE IMPLEMENTED
        Method to indicate to the protocol what the capabilities of this agent are.
        Leave it as is for the ANL 2022 competition

        Returns:
            Capabilities: Capabilities representation class
        """
        return Capabilities(
            set(["SAOP"]),
            set(["geniusweb.profile.utilityspace.LinearAdditive"]),
        )

    def getDescription(self) -> str:
        """MUST BE IMPLEMENTED
        Returns a description of your agent. 1 or 2 sentences.

        Returns:
            str: Agent description
        """
        return (
            "Increasingly random Boulwarish agent. Last second concessions based on opponent's strategy."
        )

    ##################### private support funcs #########################

    def detect_strategy(self):
        if self.filepath is not None:
            with open(self.filepath, "w") as f:
                self.summary = load(f)
            if self.summary["ubi"] >= 5:
                self.opponent_strategy = "boulware"
                self.e = 0.2 * 2**(5 - self.summary["ubi"])
            elif self.summary["aui"] <= 2:
                self.opponent_strategy = "hardline"
            else:
                self.opponent_strategy = "concede"
                self.min_util = Decimal(0.4)

    def my_turn(self):
        # Keep history of received bids and best alternative
        if self.last_received_bid is not None:
            self.received_bids.append(self.last_received_bid)
            self.received_utils.append(self.last_received_util)
            if self.last_received_util > self.best_received_util:
                self.best_received_bid = self.last_received_bid
                self.best_received_util = self.last_received_util
        # Create new bid based on the point in the negotiation and opponent's strategy
        t = self.progress.get(clock() * 1000)
        if self.summary is not None and self.opponent_strategy == "boulware" and t > 1 - (1/2)**min(self.summary["ubi"], 10):
            # If Boulware opponent is not going to concede much more, try to make a reasonable concession
            bid = self.make_concession()
        else:
            bid = self.make_bid()
        # Check if we've previously gotten a better bid already
        if self.best_received_util >= self.util_space.getUtility(bid):
            i = self.received_utils.index(self.best_received_util)
            bid = self.received_bids.pop(i)
            self.received_utils.pop(i)
            # Find next bests
            self.best_received_util = max(self.received_utils)
            i = self.received_utils.index(self.best_received_util)
            self.best_received_bid = self.received_bids[i]
        # Take action
        my_action: Action
        if bid == None or (
            self.last_received_bid != None
            and self.util_space.getUtility(self.last_received_bid)
            >= self.util_space.getUtility(bid)
        ):
            # if bid==null we failed to suggest next bid.
            my_action = Accept(self.me, self.last_received_bid)
        else:
            my_action = Offer(self.me, bid)
        self.getConnection().send(my_action)

    def make_concession(self):
        self.min_util = Decimal(0.3)
        opponent_util = self.opponent_model.get_predicted_utility(self.best_received_util)
        if self.best_received_util > self.min_util and opponent_util < 2*self.min_util:
            bid = self.best_received_bid
        else:
            bid = self.make_bid()
        return bid

    def make_bid(self) -> Bid:
        time = self.progress.get(clock() * 1000)
        utility_goal = self.get_utility_goal(time)
        options: ImmutableList[Bid] = self.extended_space.getBids(utility_goal, time)
        if options.size() == 0:
            # if we can't find good bid, get max util bid....
            options = self.extended_space.getBids(self.max_util, time)
        # pick a random one.
        return options.get(randint(0, options.size() - 1))

    def get_utility_goal(self, t: float) -> Decimal:
        ft1 = Decimal(1)
        if self.e != 0:
            ft1 = round(Decimal(1 - pow(t, 1 / self.e)), 6)  # defaults ROUND_HALF_UP
        return max(
            min((self.min_util + (self.max_util - self.min_util) * ft1), self.max_util),
            self.min_util
        )

    def terminate(self):
        self.save_data()
        self.getReporter().log(logging.INFO, "party is terminating:")
        super().terminate()
        if self.profile_int != None:
            self.profile_int.close()
            self.profile_int = None

    def save_data(self):
        ubi, aui = self.summarize_opponent()
        with open(self.filepath, "w") as f:
            dump({
                "ubi": ubi,
                "aui": aui
            }, f)

    def summarize_opponent(self):
        # Detect how much the number of unique bids is increasing
        unique_bid_index = 0
        s = round(len(self.received_bids)/2)
        left = self.received_bids[:s]
        right = self.received_bids[s:]
        while len(set(left)) > 0 and len(set(right)) > 0 and len(set(left)) < len(set(right)):
            unique_bid_index += 1
            s = round(len(right)/2)
            left = right[:s]
            right = right[s:]
        # Detect how much average utility is increasing
        avg_utility_index = 0
        s = round(len(self.received_utils)/2)
        left = self.received_utils[:s]
        right = self.received_utils[s:]
        while len(set(left)) > 0 and len(set(right)) > 0 and mean(left) < mean(right):
            avg_utility_index += 1
            s = round(len(right)/2)
            left = right[:s]
            right = right[s:]
        return unique_bid_index, avg_utility_index
