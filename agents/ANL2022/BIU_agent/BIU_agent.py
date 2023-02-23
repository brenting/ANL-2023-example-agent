import logging
import numpy as np
from pandas import array
from random import randint
from sklearn.linear_model import LinearRegression
from sklearn.ensemble import RandomForestRegressor
from sklearn.ensemble import VotingRegressor
from sklearn.neighbors import KNeighborsRegressor
from time import time
from typing import cast
import random
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
from geniusweb.profile.utilityspace.LinearAdditiveUtilitySpace import (
    LinearAdditiveUtilitySpace,
)
from geniusweb.profileconnection.ProfileConnectionFactory import (
    ProfileConnectionFactory,
)
from geniusweb.progress.ProgressTime import ProgressTime
from geniusweb.references.Parameters import Parameters
from tudelft_utilities_logging.ReportToLogger import ReportToLogger

from agents.template_agent.utils.opponent_model import OpponentModel


class BIU_agent(DefaultParty):
    """
    BIU_agent of a Python geniusweb agent.
    """
    def __init__(self):
        super().__init__()
        self.logger: ReportToLogger = self.getReporter()

        self.domain: Domain = None
        self.parameters: Parameters = None
        self.profile: LinearAdditiveUtilitySpace = None
        self.progress: ProgressTime = None
        self.me: PartyId = None
        self.other: str = None
        self.settings: Settings = None
        self.storage_dir: str = None

        self.last_received_bid: Bid = None
        self.opponent_model: OpponentModel = None
        self.logger.log(logging.INFO, "party is initialized")

        self.bids_given: list = None
        self.bids_received: list = None
        self.proposal_time: float = None
        self.opponent_bid_times: list = None

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
            profile_connection.close()

            self.opponent_bid_times = []

        # ActionDone informs you of an action (an offer or an accept)
        # that is performed by one of the agents (including yourself).
        elif isinstance(data, ActionDone):
            action = cast(ActionDone, data).getAction()
            actor = action.getActor()

            # ignore action if it is our action
            if actor != self.me:
                # obtain the name of the opponent, cutting of the position ID.
                self.other = str(actor).rsplit("_", 1)[0]

                # process action done by opponent
                self.opponent_action(action)
        # YourTurn notifies you that it is your turn to act
        elif isinstance(data, YourTurn):
            # execute a turn
            if self.proposal_time is not None:
                self.opponent_bid_times.append(self.progress.get(time() * 1000) - self.proposal_time)
            self.my_turn()
            self.proposal_time = self.progress.get(time() * 1000)

        # Finished will be send if the negotiation has ended (through agreement or deadline)
        elif isinstance(data, Finished):
            self.save_data()
            # terminate the agent MUST BE CALLED
            self.logger.log(logging.INFO, "party is terminating:")
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
        return "This is a Bar Ilan University agent that learns from the opponent's bids, by using a random forest, a linear regression and a KNN. The agent also using random stochastic to take the offers."
    
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
            # set bid as last received
            self.last_received_bid = bid

    def my_turn(self):
        """This method is called when it is our turn. It should decide upon an action
        to perform and send this action to the opponent.
        """
        if self.accept_condition(self.last_received_bid):
            action = Accept(self.me, self.last_received_bid)
        else:
            t = self.progress.get(time() * 1000)
            self.logger.log(logging.INFO, t)
            bid = self.find_bid()
            if t >= 0.95:
                t_o = self.regression_opponent_time(self.opponent_bid_times[-10:])
                self.logger.log(logging.INFO, self.opponent_bid_times)
                self.logger.log(logging.INFO, t_o)
                while all(t < 1 - t_o):
                    t = self.progress.get(time() * 1000)
            action = Offer(self.me, bid)

        self.send_action(action)

    def save_data(self):
        """This method is called after the negotiation is finished. It can be used to store data
        for learning capabilities. Note that no extensive calculations can be done within this method.
        Taking too much time might result in your agent being killed, so use it for storage only.
        """
        data = " ".join(str(x) for x in self.opponent_bid_times)
        # self_dir = "./agents/BIU_agent/data.md"
        with open(f"{self.storage_dir}/data.md", "w") as f:
            f.write(data)

    ###########################################################################################
    ################################## Example methods below ##################################
    ###########################################################################################

    def accept_condition(self, bid: Bid) -> bool:
        if bid is None:
            return False

        # progress of the negotiation session between 0 and 1 (1 is deadline)
        progress = self.progress.get(time() * 1000)

        # very basic approach that accepts if the offer is valued above 0.7 and
        # 95% of the time towards the deadline has passed
        threshold = 0.9
        if 0 < progress < 0.2:
            threshold = 0.9
        if 0.2 < progress <0.3:
            threshold = 0.8
        elif 0.3 < progress < 0.5:
            threshold = 0.6
        elif 0.5 < progress < 0.9:
            threshold = 0.5
        elif 0.9 < progress < 1:
            threshold = 0.25
        
        conditions = [
            self.profile.getUtility(bid) > 0.8
        ]
        return all(conditions)

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

    def score_bid(self, bid: Bid, alpha: float = 0.95, eps: float = 0.5) -> float:
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

        # progress = self.progress.get(time() * 1000)

        # our_utility = float(self.profile.getUtility(bid))

        # time_pressure = 1.0 - progress ** (1 / eps)
        # score = alpha * time_pressure * our_utility

        # if self.opponent_model is not None:
        #     opponent_utility = self.opponent_model.get_predicted_utility(bid)
        #     opponent_score = (1.0 - alpha * time_pressure) * opponent_utility
        #     score += opponent_score

        # return our_utility
        stochastic_alpha = 0
        stochastic_eps = 0
        STOCHASTIC_TRANSITION = random.randint(0,9)
        if 0 < STOCHASTIC_TRANSITION < 9: # alpha stay the same
            stochastic_alpha = alpha
        elif STOCHASTIC_TRANSITION == 0:
            stochastic_alpha = alpha - eps
            stochastic_eps = 0.005
        else: # STOCHASTIC_TRANSITION = 9
            stochastic_alpha = alpha + eps
            stochastic_eps = -0.005
        
        progress = self.progress.get(time() * 1000)

        utility = float(self.profile.getUtility(bid))

        time_pressure = 1.0 - progress ** (1 / eps)
        score = stochastic_alpha * time_pressure * utility

        if self.opponent_model is not None:
            opponent_utility = self.opponent_model.get_predicted_utility(bid)
            opponent_score = (1.0 - stochastic_alpha * time_pressure) * opponent_utility
            score += opponent_score
        if utility > 0.994 and stochastic_eps > 0:
            stochastic_eps = 0
        if utility < 0.005 and stochastic_eps < 0:
            stochastic_eps = 0
        final_score = utility + stochastic_eps
        return final_score
        


    def regression_opponent_time(self, bid_times):
        r1 = LinearRegression()
        r2 = RandomForestRegressor(n_estimators=10, random_state=1)
        r3 = KNeighborsRegressor()
        X = array(range(len(bid_times))).reshape(-1, 1)
        y = array(bid_times).reshape(-1, 1)
        er = VotingRegressor([('lr', r1), ('rf', r2), ('r3', r3)])        
        return er.fit(X, y).predict(X)