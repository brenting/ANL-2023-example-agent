#######################################################
# author: Arash Ebrahimnezhad
# Email: Arash.ebrah@gmail.com
#######################################################
import json
import logging
from random import randint
import random
from time import time
from tkinter.messagebox import NO
from typing import cast
import math
import pickle
import os
from statistics import mean
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
from tudelft.utilities.immutablelist.ImmutableList import ImmutableList
from .utils.opponent_model import OpponentModel
from geniusweb.profile.utilityspace.LinearAdditive import LinearAdditive
from agents.time_dependent_agent.extended_util_space import ExtendedUtilSpace
from decimal import Decimal
from geniusweb.opponentmodel import FrequencyOpponentModel


NUMBER_OF_GOALS = 5


class LuckyAgent2022(DefaultParty):
    """
    Template of a Python geniusweb agent.
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

        self.received_bid_details = []
        self.my_bid_details = []
        self.best_received_bid = None

        self.logger.log(logging.INFO, "party is initialized")
        self.alpha = 1.0
        self.betta = 0.0
        # self.pattern = randint(0, PATTERN_SIZE)
        self.agreement_utility = 0.0
        self._utilspace: LinearAdditive = None  # type:ignore
        self.who_accepted = None

        self.is_called = False

        # ************* Parameters *************
        self.max = 1.0
        self.min = 0.6
        self.e = 0.05
        self.increasing_e = 0.025
        self.decreasing_e = 0.025
        self.epsilon = 1.0
        self.good_agreement_u = 0.95
        self.condition_d = 0

    def ff(self, ll, n):
        x_list = []
        for x in ll[::-1]:
            if x[1] == n:
                x_list.append(x[0])
            else:
                break
        if len(x_list) > 0:
            m = mean(x_list)
        else:
            m = 0.8
        return m

    def set_parameters(self, opp):
        if not self.other or not os.path.exists(f"{self.storage_dir}/m_data_{self.other}"):
            self.min = 0.6
            self.e = 0.05
        else:
            rand_num = random.random()
            saved_data = self.return_saved_data(f'm_data_{self.other}')
            condition_data = self.return_saved_data(f'c_data_{self.other}')
            if opp in saved_data:
                self.good_agreement_u = self.good_agreement_u - \
                    (len(saved_data[opp]) * 0.01)
                if self.good_agreement_u < 0.7:
                    self.good_agreement_u = 0.7
                if len(saved_data[opp]) >= 2:
                    if (saved_data[opp][-2][0] == 0 and saved_data[opp][-1][0] > 0) or ((saved_data[opp][-2][1] == saved_data[opp][-1][1]) and (saved_data[opp][-2][2] == saved_data[opp][-1][2])):
                        self.condition_d = condition_data[opp] + \
                            saved_data[opp][-1][0]
                        if 0 <= self.condition_d < 1:
                            self.condition_d = 1
                        self.epsilon = self.epsilon / self.condition_d
                        if rand_num > self.epsilon:
                            self.min = saved_data[opp][-1][1]
                            self.e = saved_data[opp][-1][2]
                        else:
                            if saved_data[opp][-1][0] > 0 and saved_data[opp][-1][0] < self.good_agreement_u:
                                self.min = saved_data[opp][-1][1] + \
                                    self.increasing_e
                                if self.min > 0.7:
                                    self.min = 0.7
                                self.e = saved_data[opp][-1][2] - \
                                    self.increasing_e
                                if self.e < 0.005:
                                    self.e = 0.005
                            if saved_data[opp][-1][0] == 0:
                                self.condition_d = condition_data[opp] - (
                                    1-self.ff(saved_data[opp], saved_data[opp][-1][1]))
                                if self.condition_d < 0:
                                    self.condition_d = 0
                                self.min = saved_data[opp][-1][1] - \
                                    self.decreasing_e
                                if self.min < 0.5:
                                    self.min = 0.5
                                self.e = saved_data[opp][-1][2] + \
                                    self.decreasing_e
                                if self.e > 0.1:
                                    self.e = 0.1
                            if saved_data[opp][-1][0] >= self.good_agreement_u:
                                self.min = saved_data[opp][-1][1]
                                self.e = saved_data[opp][-1][2]
                    else:
                        if saved_data[opp][-1][0] > 0 and saved_data[opp][-1][0] < self.good_agreement_u:
                            self.min = saved_data[opp][-1][1] + \
                                self.increasing_e
                            if self.min > 0.7:
                                self.min = 0.7
                            self.e = saved_data[opp][-1][2] - self.increasing_e
                            if self.e < 0.005:
                                self.e = 0.005
                        if saved_data[opp][-1][0] == 0:
                            self.condition_d = condition_data[opp] - (
                                1-self.ff(saved_data[opp], saved_data[opp][-1][1]))
                            if self.condition_d < 0:
                                self.condition_d = 0
                            self.min = saved_data[opp][-1][1] - \
                                self.decreasing_e
                            if self.min < 0.5:
                                self.min = 0.5
                            self.e = saved_data[opp][-1][2] + self.decreasing_e
                            if self.e > 0.1:
                                self.e = 0.1
                        if saved_data[opp][-1][0] >= self.good_agreement_u:
                            self.min = saved_data[opp][-1][1]
                            self.e = saved_data[opp][-1][2]
                else:
                    if saved_data[opp][-1][0] > 0 and saved_data[opp][-1][0] < self.good_agreement_u:
                        self.min = saved_data[opp][-1][1] + self.increasing_e
                        if self.min > 0.7:
                            self.min = 0.7
                        self.e = saved_data[opp][-1][2] - self.increasing_e
                        if self.e < 0.005:
                            self.e = 0.005
                    if saved_data[opp][-1][0] == 0:
                        self.condition_d = condition_data[opp] - (
                            1-self.ff(saved_data[opp], saved_data[opp][-1][1]))
                        if self.condition_d < 0:
                            self.condition_d = 0
                        self.min = saved_data[opp][-1][1] - self.decreasing_e
                        if self.min < 0.5:
                            self.min = 0.5
                        self.e = saved_data[opp][-1][2] + self.decreasing_e
                        if self.e > 0.1:
                            self.e = 0.1
                    if saved_data[opp][-1][0] >= self.good_agreement_u:
                        self.min = saved_data[opp][-1][1]
                        self.e = saved_data[opp][-1][2]
            else:
                self.min = 0.6
                self.e = 0.05

    def return_saved_data(self, file_name):
        # for reading also binary mode is important
        file = open(f"{self.storage_dir}/{file_name}", 'rb')
        saved_data = json.load(file)
        file.close()
        return saved_data

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

            # initialize FrequencyOpponentModel
            self.opponent_model = FrequencyOpponentModel.FrequencyOpponentModel.create().With(
                newDomain=self.profile.getDomain(),
                newResBid=self.profile.getReservationBid())

            profile_connection.close()

        # ActionDone informs you of an action (an offer or an accept)
        # that is performed by one of the agents (including yourself).
        elif isinstance(data, ActionDone):
            action = cast(ActionDone, data).getAction()

            actor = action.getActor()

            if isinstance(action, Accept):
                # print(str(actor).rsplit("_", 1)[0], '=>', cast(Offer, action).getBid())
                agreement_bid = cast(Offer, action).getBid()
                self.agreement_utility = float(
                    self.profile.getUtility(agreement_bid))
                self.who_accepted = str(actor).rsplit("_", 1)[0]

            # ignore action if it is our action
            if actor != self.me:
                # obtain the name of the opponent, cutting of the position ID.
                self.other = str(actor).rsplit("_", 1)[0]

                # set parameters according of saved data
                if not self.is_called:
                    self.set_parameters(self.other)
                    self.is_called = True

                # process action done by opponent
                self.opponent_action(action)
        # YourTurn notifies you that it is your turn to act
        elif isinstance(data, YourTurn):
            # execute a turn
            self.my_turn()

        # Finished will be send if the negotiation has ended (through agreement or deadline)
        elif isinstance(data, Finished):
            if self.other:
                self.save_data()
            # terminate the agent MUST BE CALLED
            self.logger.log(logging.INFO, "party is terminating:")
            super().terminate()
        else:
            self.logger.log(logging.WARNING,
                            "Ignoring unknown info " + str(data))

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
        return "LuckyAgent2022"

    def opponent_action(self, action):
        """Process an action that was received from the opponent.
        Args:
            action (Action): action of opponent
        """
        # if it is an offer, set the last received bid
        if isinstance(action, Offer):

            bid = cast(Offer, action).getBid()

            # update opponent model with bid
            self.opponent_model = self.opponent_model.WithAction(
                action=action, progress=self.progress)
            # set bid as last received
            self.last_received_bid = bid
            # self.received_bids.append(bid)
            self.received_bid_details.append(BidDetail(
                bid, float(self.profile.getUtility(bid))))

    def my_turn(self):
        """This method is called when it is our turn. It should decide upon an action
        to perform and send this action to the opponent.
        """
        self.cal_thresholds()
        self._updateUtilSpace()

        next_bid = self.find_bid()
        # check if the last received offer is good enough
        if self.accept_condition(self.last_received_bid, next_bid):
            # if so, accept the offer
            action = Accept(self.me, self.last_received_bid)
        else:
            # if not, find a bid to propose as counter offer
            action = Offer(self.me, next_bid)
            # self.my_bids.append(next_bid)
            self.my_bid_details.append(
                BidDetail(next_bid, float(self.profile.getUtility(next_bid))))

        # send the action
        self.send_action(action)

    def _updateUtilSpace(self) -> LinearAdditive:  # throws IOException
        newutilspace = self.profile
        if not newutilspace == self._utilspace:
            self._utilspace = cast(LinearAdditive, newutilspace)
            self._extendedspace = ExtendedUtilSpace(self._utilspace)
        return self._utilspace

    def save_data(self):
        """This method is called after the negotiation is finished. It can be used to store data
        for learning capabilities. Note that no extensive calculations can be done within this method.
        Taking too much time might result in your agent being killed, so use it for storage only.
        """
        # **************************************************

        c_data = {}
        if os.path.isfile(f"{self.storage_dir}/c_data_{self.other}"):
            # OLD
            # dbfile_c = open(f"{self.storage_dir}/c_data", 'rb')
            # c_data = pickle.load(dbfile_c)
            # dbfile_c.close()
            # NEW
            with open(f"{self.storage_dir}/c_data_{self.other}", 'r') as dbfile_c:
                c_data = json.load(dbfile_c)

        if os.path.exists(f"{self.storage_dir}/c_data_{self.other}"):
            os.remove(f"{self.storage_dir}/c_data_{self.other}")

        c_data[self.other] = self.condition_d
        # OLD
        # dbfile_c = open(f"{self.storage_dir}/c_data", 'ab')
        # pickle.dump(c_data, dbfile_c)
        # dbfile_c.close()
        # NEW
        with open(f"{self.storage_dir}/c_data_{self.other}", 'w') as dbfile_c:
            json.dump(c_data, dbfile_c, indent=2)

        m_data = {}
        if os.path.isfile(f"{self.storage_dir}/m_data_{self.other}"):
            # OLD
            # dbfile = open(f"{self.storage_dir}/m_data", 'rb')
            # m_data = pickle.load(dbfile)
            # dbfile.close()
            # NEW
            with open(f"{self.storage_dir}/m_data_{self.other}", 'r') as dbfile:
                m_data = json.load(dbfile)


        if os.path.exists(f"{self.storage_dir}/m_data_{self.other}"):
            os.remove(f"{self.storage_dir}/m_data_{self.other}")

        m_tuple = (self.agreement_utility, self.min, self.e)
        if self.other in m_data:
            m_data[self.other].append(m_tuple)
        else:
            m_data[self.other] = [m_tuple, ]

        # OLD
        # dbfile = open(f"{self.storage_dir}/m_data", 'ab')
        # # source, destination
        # pickle.dump(m_data, dbfile)
        # dbfile.close()
        # NEW
        with open(f"{self.storage_dir}/m_data_{self.other}", 'w') as dbfile:
            json.dump(m_data, dbfile, indent=2)

    ###########################################################################################
    ################################## Example methods below ##################################
    ###########################################################################################

    def accept_condition(self, received_bid: Bid, next_bid) -> bool:
        if received_bid is None:
            return False

        progress = self.progress.get(time() * 1000)

        # set reservation value
        if self.profile.getReservationBid() is None:
            reservation = 0.0
        else:
            reservation = self.profile.getUtility(
                self.profile.getReservationBid())

        received_bid_utility = self.profile.getUtility(received_bid)
        condition1 = received_bid_utility >= self.threshold_acceptance and received_bid_utility >= reservation
        condition2 = progress > 0.97 and received_bid_utility > self.min and received_bid_utility >= reservation
        condition3 = self.alpha*float(received_bid_utility) + self.betta >= float(
            self.profile.getUtility(next_bid)) and received_bid_utility >= reservation

        return condition1 or condition2 or condition3

    def find_bid(self) -> Bid:
        """
        @return next possible bid with current target utility, or null if no such
                bid.
        """
        interval = self.threshold_high - self.threshold_low
        s = interval / NUMBER_OF_GOALS

        utility_goals = []
        for i in range(NUMBER_OF_GOALS):
            utility_goals.append(self.threshold_low+s*i)
        utility_goals.append(self.threshold_high)

        options: ImmutableList[Bid] = self._extendedspace.getBids(
            Decimal(random.choice(utility_goals)))

        opponent_utilities = []
        for option in options:
            if self.opponent_model != None:
                opp_utility = float(
                    self.opponent_model.getUtility(option))
                if opp_utility > 0:
                    opponent_utilities.append(opp_utility)
                else:
                    opponent_utilities.append(0.00001)
            else:
                opponent_utilities.append(0.00001)

        if options.size() == 0:
            # if we can't find good bid, get max util bid....
            options = self._extendedspace.getBids(self._extendedspace.getMax())
            return options.get(randint(0, options.size() - 1))
        # pick a random one.

        next_bid = random.choices(list(options), weights=opponent_utilities)[0]
        for bid_detaile in self.received_bid_details:
            if bid_detaile.getUtility() >= self.profile.getUtility(next_bid):
                next_bid = bid_detaile.getBid()

        return random.choices(list(options), weights=opponent_utilities)[0]

    # ************************************************************
    def f(self, t, k, e):
        return k + (1-k)*(t**(1/e))

    def p(self, min1, max1, e, t):
        return min1 + (1-self.f(t, 0, e))*(max1-min1)

    def cal_thresholds(self):
        progress = self.progress.get(time() * 1000)
        self.threshold_high = self.p(self.min+0.1, self.max, self.e, progress)
        self.threshold_acceptance = self.p(
            self.min+0.1, self.max, self.e, progress) - (0.1*((progress+0.0000001)))
        self.threshold_low = self.p(self.min+0.1, self.max, self.e, progress) - \
            (0.1*((progress+0.0000001))) * abs(math.sin(progress * 60))

    # ================================================================
    def get_domain_size(self, domain: Domain):
        domain_size = 1
        for issue in domain.getIssues():
            domain_size *= domain.getValues(issue).size()
        return domain_size
    # ================================================================


class BidDetail:
    def __init__(self, bid: Bid, utility: float):
        self.__bid = bid
        self.__utiltiy = utility

    def getBid(self):
        return self.__bid

    def getUtility(self):
        return self.__utiltiy

    def __repr__(self) -> str:
        return f'{self.__bid}: {self.__utiltiy}'
