import json
import random
import logging
from random import randint
from time import time
from typing import cast
from utils.plot_trace import plot_trace
from utils.runners import run_session
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

from .utils.opponent_model import OpponentModel


class Tjaronchery10Agent(DefaultParty):
    """
    Template of a Python geniusweb agent.
    """

    def __init__(self):
        super().__init__()
        self.logger: ReportToLogger = self.getReporter()
        self.tatic = 1
        self.domain: Domain = None
        self.parameters: Parameters = None
        self.profile: LinearAdditiveUtilitySpace = None
        self.progress: ProgressTime = None
        self.me: PartyId = None
        self.other: str = None
        self.settings: Settings = None
        self.storage_dir: str = None
        self.datii = ""
        self.last_received_bid: Bid = None
        self.counter = 0
        self.minicount = 0
        self.flag = 0
        self.dupli = 0.00
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

        # ActionDone informs you of an action (an offer or an accept)
        # that is performed by one of the agents (including yourself).
        elif isinstance(data, ActionDone):
            action = cast(ActionDone, data).getAction()
            actor = action.getActor()

            # ignore action if it is our action
            if actor != self.me:
                # obtain the name of the opponent, cutting of the position ID.
                self.other = str(actor).rsplit("_", 1)[0]

                if self.counter > 3:
                    with open(f"{self.storage_dir}/{self.other}datatactic.txt", "r") as t:
                        shura = t.readline()
                        if shura.__contains__("tac2"):
                            self.tatic = 2
                            t.close()
                        else:
                            with open(f"{self.storage_dir}/{self.other}data.txt", "r") as f:
                                lines = f.readlines()
                                last_lines = lines[-3:]
                                if last_lines[0] == '0\n' and last_lines[1] == '0\n' and last_lines[2] == '0\n':
                                    # print("THIS IS MACABBIIIIIIIIIIIIIIIIIIIIIII")
                                    self.tatic = 2
                                    with open(f"{self.storage_dir}/{self.other}datatactic.txt", "a") as x:
                                        x.write("tac2")
                                        x.close()
                                else:
                                    self.tatic = 1
                                f.close()
                self.flag = 1
                # process action done by opponent
                self.opponent_action(action)
        # YourTurn notifies you that it is your turn to act
        elif isinstance(data, YourTurn):
            # execute a turn
            self.my_turn()

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
        return "mine agent for the ANL 2022 competition"

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
        # check if the last received offer is good enough
        if self.minicount == 0:
            try:
                with open(f"{self.storage_dir}/{self.other}counter.txt", "r") as tt:
                    a = 1
                    content = tt.readlines()
                    tt.close()
                    for line in content:
                        for i in line:
                            # Checking for the digit in
                            # the string
                            if i.isdigit() == True:
                                a += int(i)
                    num = a
                    self.counter = num
                    print("this is macabiiiiiiiiiiiiiii")
                    print(num)
                try:
                    with open(f"{self.storage_dir}/{self.other}counter.txt", "w") as ttt:
                        ttt.write(num.__str__())
                        ttt.close()
                except FileNotFoundError:
                    print("file does not exist1 :(")
            except FileNotFoundError:
                print("file does not exist counter :(")
        self.minicount = 1

        if self.accept_condition(self.last_received_bid):
            # if so, accept the offer
            self.datii = self.profile.getUtility(self.last_received_bid).__str__()
            action = Accept(self.me, self.last_received_bid)
        else:
            # if not, find a bid to propose as counter offer
            bid = self.find_bid()

            action = Offer(self.me, bid)
            self.datii = self.profile.getUtility(bid).__str__()

        # send the action
        self.send_action(action)

    def save_data(self):
        """This method is called after the negotiation is finished. It can be used to store data
        for learning capabilities. Note that no extensive calculations can be done within this method.
        Taking too much time might result in your agent being killed, so use it for storage only.
        """
        data = "Data for learning (see README.md)"
        progress = self.progress.get(time() * 1000)
        s = self.datii
        t = self.me.__str__()
        r = self.settings.getID().__str__()
        y = self.other
        # path = self.storage_dir
        # path = f"{self.storage_dir}/{y}"
        # print(path)

        if progress == 1:
            s = 0
        with open(f"{self.storage_dir}/{y}data.txt", "a") as f:
            f.write(f"{s}\n")
            f.close()
        with open(f"{self.storage_dir}/{y}datatactic.txt", "a") as t:
            t.close()
        if self.counter == 0:
            print("OPEN FILEEEEEEEEE")
            with open(f"{self.storage_dir}/{y}counter.txt", "a") as x:
                x.write("1\n")
                x.close()


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
        # rand_b = 0.9
        my_bid = self.find_bid()
        # num = self.profile.getUtility(my_bid)
        if self.tatic == 2:
            conditions = [
                self.profile.getUtility(bid) > 0.25,
                progress > 0.8
            ]

        else:
            conditions = [
                self.profile.getUtility(bid) > 0.9,
                # progress > 0.8,
            ]
        return all(conditions)

    def find_bid(self) -> Bid:
        # compose a list of all possible bids
        domain = self.profile.getDomain()
        all_bids = AllBidsList(domain)

        best_bid_score = 0.0
        best_bid = None

        # take 500 attempts to find a bid according to a heuristic score
        if self.tatic == 2:
            for _ in range(1000):
                bid = all_bids.get(randint(0, all_bids.size() - 1))
                bid_score = self.score_bid(bid)
                #bid_score = self.profile.getUtility(bid)

                if  0.5 < bid_score < 0.9:
                    best_bid_score, best_bid = bid_score, bid

        else:
            for _ in range(1000):
                bid = all_bids.get(randint(0, all_bids.size() - 1))
                # bid_score = self.score_bid(bid)
                bid_score = self.profile.getUtility(bid)
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

        time_pressure = 0.8 - progress ** (1 / eps)
        score = alpha * time_pressure * our_utility
        #score = our_utility

        if self.opponent_model is not None:
            opponent_utility = self.opponent_model.get_predicted_utility(bid)
            opponent_score = (1.0 - alpha * time_pressure) * opponent_utility
            score += opponent_score

        return score
