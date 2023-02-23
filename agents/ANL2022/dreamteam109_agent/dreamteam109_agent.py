import datetime
import json
import logging
from math import floor
from random import randint
import time
from decimal import Decimal
from os import path
from typing import TypedDict, cast

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
from geniusweb.issuevalue.Bid import Bid
from geniusweb.issuevalue.Domain import Domain
from geniusweb.party.Capabilities import Capabilities
from geniusweb.party.DefaultParty import DefaultParty
from geniusweb.issuevalue.Value import Value
from geniusweb.profile.utilityspace.LinearAdditiveUtilitySpace import (
    LinearAdditiveUtilitySpace,
)
from geniusweb.profileconnection.ProfileConnectionFactory import (
    ProfileConnectionFactory,
)
from geniusweb.progress.ProgressTime import ProgressTime
from geniusweb.references.Parameters import Parameters
from tudelft_utilities_logging.ReportToLogger import ReportToLogger
from .utils.logger import Logger

from .utils.opponent_model import OpponentModel
from .utils.utils import bid_to_string

class SessionData(TypedDict):
    progressAtFinish: float
    utilityAtFinish: float
    didAccept: bool
    isGood: bool
    topBidsPercentage: float
    forceAcceptAtRemainingTurns: float

class DataDict(TypedDict):
    sessions: list[SessionData]

class DreamTeam109Agent(DefaultParty):

    def __init__(self):
        super().__init__()
        self.logger: Logger = Logger(self.getReporter(), id(self))

        self.domain: Domain = None
        self.parameters: Parameters = None
        self.profile: LinearAdditiveUtilitySpace = None
        self.progress: ProgressTime = None
        self.me: PartyId = None
        self.other: PartyId = None
        self.other_name: str = None
        self.settings: Settings = None
        self.storage_dir: str = None

        self.data_dict: DataDict = None

        self.last_received_bid: Bid = None
        self.opponent_model: OpponentModel = None
        self.all_bids: AllBidsList = None
        self.bids_with_utilities: list[tuple[Bid, float]] = None
        self.num_of_top_bids: int = 1
        self.min_util: float = 0.9

        self.round_times: list[Decimal] = []
        self.last_time = None
        self.avg_time = None
        self.utility_at_finish: float = 0
        self.did_accept: bool = False
        self.top_bids_percentage: float = 1 / 300
        self.force_accept_at_remaining_turns: float = 1
        self.force_accept_at_remaining_turns_light: float = 1
        self.opponent_best_bid: Bid = None
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
        if isinstance(data, Settings):
            self.settings = cast(Settings, data)
            self.me = self.settings.getID()

            # progress towards the deadline has to be tracked manually through the use of the Progress object
            self.progress = self.settings.getProgress()

            self.parameters = self.settings.getParameters()
            self.storage_dir = self.parameters.get("storage_dir")

            # the profile contains the preferences of the agent over the domain
            profile_connection = ProfileConnectionFactory.create(
                data.getProfile().getURI(), self.getReporter()
            )
            self.profile = profile_connection.getProfile()
            self.domain = self.profile.getDomain()
            # compose a list of all possible bids
            self.all_bids = AllBidsList(self.domain)

            profile_connection.close()

        # ActionDone informs you of an action (an offer or an accept)
        # that is performed by one of the agents (including yourself).
        elif isinstance(data, ActionDone):
            action = cast(ActionDone, data).getAction()
            actor = action.getActor()

            # ignore action if it is our action
            if actor != self.me:
                if self.other is None:
                    self.other = actor
                    # obtain the name of the opponent, cutting of the position ID.
                    self.other_name = str(actor).rsplit("_", 1)[0]
                    self.attempt_load_data()
                    self.learn_from_past_sessions(self.data_dict["sessions"])

                # process action done by opponent
                self.opponent_action(action)
        # YourTurn notifies you that it is your turn to act
        elif isinstance(data, YourTurn):
            # execute a turn
            self.my_turn()

        # Finished will be send if the negotiation has ended (through agreement or deadline)
        elif isinstance(data, Finished):
            agreements = cast(Finished, data).getAgreements()
            if len(agreements.getMap()) > 0:
                agreed_bid = agreements.getMap()[self.me]
                self.logger.log(logging.INFO, "agreed_bid = " + bid_to_string(agreed_bid))
                self.utility_at_finish = float(self.profile.getUtility(agreed_bid))
            else:
                self.logger.log(logging.INFO, "no agreed bid (timeout? some agent crashed?)")
            
            self.update_data_dict()
            self.save_data()

            # terminate the agent MUST BE CALLED
            self.logger.log(logging.INFO, "party is terminating")
            super().terminate()
        else:
            self.logger.log(logging.WARNING, "Ignoring unknown info " + str(data))

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
        return "DreamTeam109 agent for the ANL 2022 competition"

    def opponent_action(self, action):
        """Process an action that was received from the opponent.

        Args:
            action (Action): action of opponent
        """
        # if it is an offer, set the last received bid
        if isinstance(action, Offer):
            # create opponent model if it was not yet initialised
            if self.opponent_model is None:
                self.opponent_model = OpponentModel(self.domain, self.logger)

            bid = cast(Offer, action).getBid()

            # update opponent model with bid
            self.opponent_model.update(bid)
            # set bid as last received
            self.last_received_bid = bid

            if self.opponent_best_bid is None:
                self.opponent_best_bid = bid
            elif self.profile.getUtility(bid) > self.profile.getUtility(self.opponent_best_bid):
                self.opponent_best_bid = bid

    def my_turn(self):
        """This method is called when it is our turn. It should decide upon an action
        to perform and send this action to the opponent.
        """

        # For calculating average time per round
        if self.last_time is not None:
            self.round_times.append(datetime.datetime.now().timestamp() - self.last_time.timestamp())
            self.avg_time = sum(self.round_times[-3:])/3
        self.last_time = datetime.datetime.now()

        # check if the last received offer is good enough
        # if self.accept_condition(self.last_received_bid):
        if self.accept_condition(self.last_received_bid):
            self.logger.log(logging.INFO, "accepting bid : " + bid_to_string(self.last_received_bid))
            # if so, accept the offer
            action = Accept(self.me, self.last_received_bid)
            self.did_accept = True
        else:
            # if not, find a bid to propose as counter offer
            bid = self.find_bid()
            self.logger.log(logging.INFO, "Offering bid : " + bid_to_string(bid))
            action = Offer(self.me, bid)

        # send the action
        self.send_action(action)

    def get_data_file_path(self) -> str:
        return f"{self.storage_dir}/{self.other_name}.json"

    def attempt_load_data(self):
        if path.exists(self.get_data_file_path()):
            with open(self.get_data_file_path()) as f:
                self.data_dict = json.load(f)
            self.logger.log(logging.INFO, "Loaded previous data about opponent: " + self.other_name)
            self.logger.log(logging.INFO, "data_dict = " + str(self.data_dict))
        else:
            self.logger.log(logging.WARN, "No previous data saved about opponent: " + self.other_name)
            # initialize an empty data dict
            self.data_dict = {
                "sessions": []
            }

    def update_data_dict(self):
        # NOTE: We shouldn't do extensive calculations in this method (see note in save_data method)

        progress_at_finish = self.progress.get(time.time() * 1000)

        session_data: SessionData = {
            "progressAtFinish": progress_at_finish,
            "utilityAtFinish": self.utility_at_finish,
            "didAccept": self.did_accept,
            "isGood": self.utility_at_finish >= self.min_util,
            "topBidsPercentage": self.top_bids_percentage,
            "forceAcceptAtRemainingTurns": self.force_accept_at_remaining_turns
        }

        self.logger.log(logging.INFO, "Updating data dict with session data: " + str(session_data))
        self.data_dict["sessions"].append(session_data)

    def save_data(self):
        """This method is called after the negotiation is finished. It can be used to store data
        for learning capabilities. Note that no extensive calculations can be done within this method.
        Taking too much time might result in your agent being killed, so use it for storage only.
        """
        if self.other_name is None:
            self.logger.log(logging.WARNING, "Opponent name was not set; skipping save data")
        else:
            json_data = json.dumps(self.data_dict, sort_keys=True, indent=4)
            with open(self.get_data_file_path(), "w") as f:
                f.write(json_data)
            self.logger.log(logging.INFO, "Saved data about opponent: " + self.other_name)

    def learn_from_past_sessions(self, sessions: list[SessionData]):
        accept_levels = [0, 0, 1, 1.1]
        light_accept_levels = [0, 1, 1.1]
        top_bids_levels = [1 / 300, 1 / 100, 1 / 30]
                
        self.force_accept_at_remaining_turns = accept_levels[min(len(accept_levels) - 1, len(list(filter(self.did_fail, sessions))))]
        self.force_accept_at_remaining_turns_light = light_accept_levels[min(len(light_accept_levels) - 1, len(list(filter(self.did_fail, sessions))))]
        self.top_bids_percentage =  top_bids_levels[min(len(top_bids_levels) - 1, len(list(filter(self.low_utility, sessions))))]
        
    def did_fail(self, session: SessionData):
        return session["utilityAtFinish"] == 0

    def low_utility(self, session: SessionData):
        return session["utilityAtFinish"] < 0.5

    def accept_condition(self, bid: Bid) -> bool:
        if bid is None:
            return False

        # progress of the negotiation session between 0 and 1 (1 is deadline)
        progress = self.progress.get(time.time() * 1000)
        threshold = 0.98
        light_threshold = 0.95

        if self.avg_time is not None: 
            threshold = 1 - 1000 * self.force_accept_at_remaining_turns * self.avg_time / self.progress.getDuration()
            light_threshold = 1 - 5000 * self.force_accept_at_remaining_turns_light * self.avg_time / self.progress.getDuration()

        conditions = [
            self.profile.getUtility(bid) >= self.min_util,
            progress >= threshold,
            progress > light_threshold and self.profile.getUtility(bid) >= self.bids_with_utilities[floor(len(self.bids_with_utilities) / 5) - 1][1]
        ]
        return any(conditions)

    def find_bid(self) -> Bid:
        self.logger.log(logging.INFO, "finding bid...")

        num_of_bids = self.all_bids.size()

        if self.bids_with_utilities is None:
            self.logger.log(logging.INFO, "calculating bids_with_utilities...")
            startTime = time.time()
            self.bids_with_utilities = []

            for index in range(num_of_bids):
                bid = self.all_bids.get(index)
                bid_utility = float(self.profile.getUtility(bid))
                self.bids_with_utilities.append((bid, bid_utility))
            
            self.bids_with_utilities.sort(key=lambda tup: tup[1], reverse=True)
            
            endTime = time.time()
            self.logger.log(logging.INFO, "calculating bids_with_utilities took (in seconds): " + str(endTime - startTime))

            self.num_of_top_bids = max(5, num_of_bids * self.top_bids_percentage)
            
        if (self.last_received_bid is None):
            return self.bids_with_utilities[0][0]

        progress = self.progress.get(time.time() * 1000)
        light_threshold = 0.95

        if self.avg_time is not None: 
            light_threshold = 1 - 5000 * self.force_accept_at_remaining_turns_light * self.avg_time / self.progress.getDuration()

        if (progress > light_threshold):
            return self.opponent_best_bid

        if (num_of_bids < self.num_of_top_bids):
            self.num_of_top_bids = num_of_bids / 2

        self.min_util = self.bids_with_utilities[floor(self.num_of_top_bids) - 1][1]
        self.logger.log(logging.INFO, "min_util = " + str(self.min_util))
        
        picked_ranking = randint(0, floor(self.num_of_top_bids) - 1)

        return self.bids_with_utilities[picked_ranking][0]

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
        progress = self.progress.get(time.time() * 1000)

        our_utility = float(self.profile.getUtility(bid))

        time_pressure = 1.0 - progress ** (1 / eps)
        score = alpha * time_pressure * our_utility

        if self.opponent_model is not None:
            opponent_utility = self.opponent_model.get_predicted_utility(bid)
            opponent_score = (1.0 - alpha * time_pressure) * opponent_utility
            score += opponent_score

        return score
