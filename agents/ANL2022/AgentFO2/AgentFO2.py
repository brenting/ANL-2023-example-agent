import csv
import logging
import os
from random import randint
from time import time
from typing import cast

from geniusweb.actions.Accept import Accept
from geniusweb.actions.Action import Action
from geniusweb.actions.Offer import Offer
from geniusweb.actions.PartyId import PartyId
from geniusweb.bidspace.BidsWithUtility import BidsWithUtility
from geniusweb.bidspace.Interval import Interval
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
from geniusweb.profile.utilityspace.LinearAdditive import LinearAdditive
from geniusweb.profileconnection.ProfileConnectionFactory import (
    ProfileConnectionFactory,
)
from geniusweb.progress.ProgressTime import ProgressTime
from geniusweb.references.Parameters import Parameters
from tudelft_utilities_logging.ReportToLogger import ReportToLogger
from tudelft.utilities.immutablelist.ImmutableList import ImmutableList
from decimal import Decimal



class AgentFO2(DefaultParty):
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
        self.allbid:BidsWithUtility = None

        self.pre_opponent_bid_hamming=None
        self.pre_opponent_utility_log=None
        self.which_pre_accept=None
        self.pre_strategy=None

        self.last_received_bid: Bid = None
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
            self.opponent_utility_log=[]
            self.opponent_bid_hamming=[]
            self.opponent_strategy=-1
            self.which_accept=[-1,0,0]
            self.read_data=True
            self.strategy_set_FLAG=True
            self.min=0.5
            self.accept_utilgoal=0.8
            self.random_max=1.0
            self.not_accept=0.05
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
            self.issue=self.domain.getIssuesValues()
            self.allbid = BidsWithUtility.create(cast(LinearAdditive,self.profile))
            profile_connection.close()

        # ActionDone informs you of an action (an offer or an accept)
        # that is performed by one of the agents (including yourself).
        elif isinstance(data, ActionDone):
            action = cast(ActionDone, data).getAction()
            actor = action.getActor()
            # ignore action if it is our action
            if actor != self.me:
                # obtain the name of the opponent, cutting of the position ID.
                self.other = str(actor).split("_")[-2]

                # read data
                if self.read_data and os.path.exists(f"{self.storage_dir}/{self.other}.csv"):
                    with open(f"{self.storage_dir}/{self.other}.csv","r") as f:
                        reader=csv.reader(f)
                        l=[row for row in reader]
                        l=[[float(v) for v in row] for row in l]
                    self.pre_opponent_utility_log=l[0]
                    self.pre_opponent_bid_hamming=l[1]
                    self.which_pre_accept=l[2]
                    self.pre_strategy=l[3]
                    self.accept_utilgoal=max(0.8,self.which_pre_accept[1])
                    self.opponent_strategy_search()
                self.read_data=False

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

    def opponent_strategy_search(self):
        if len(self.pre_opponent_bid_hamming)>=20:
            x=2
            while not self.pre_opponent_bid_hamming.count(x):
                x+=1
                if x>8:
                    x=1
                    break
            if x>=2:
                ind=self.pre_opponent_bid_hamming.index(x)
            else:
                ind=-1

            if ind>=20:
                # opponent strategy is time-dipendent
                self.opponent_strategy=0
            elif ind>=0:
                # opponent strategy is random or others
                count=0
                x=min(20,len(self.pre_opponent_bid_hamming))
                for i in range(x):
                    if self.pre_opponent_bid_hamming[i]>=2:
                        count+=1
                if count>=10:
                    self.opponent_strategy=1
                else:
                    self.opponent_strategy=2
            else:
                # opponent strategy is others
                self.opponent_strategy=2
        else:
            self.opponent_strategy=self.pre_strategy[0]
            if self.opponent_strategy==-1:
                self.opponent_strategy=2

    def my_strategy_setting(self):
        self.opponent_one=self.profile.getUtility(self.last_received_bid)
        if self.which_pre_accept:
            if self.opponent_strategy==0: # when opponent strategy is time-dependent
                if self.which_pre_accept[0]==0: # pre-accept is me
                    pre_acc_util=self.which_pre_accept[2]
                    sup_util=self.utility_suppose(pre_acc_util)
                    self.min=min(sup_util,pre_acc_util)
                elif self.which_pre_accept[0]==1: # pre-accept is opponent
                    pre_acc_util=self.which_pre_accept[2]
                    sup_util=self.utility_suppose(pre_acc_util)
                    self.min=max(sup_util,pre_acc_util)
                    self.min=min(self.min,0.9)
                else: # pre-accept is unknown or None
                    self.min=self.pre_strategy[1]-0.05
            elif self.opponent_strategy==1: # when opponent strategy is random
                if self.which_pre_accept[0]<=0: # pre-accept is me or None or unkown
                    self.accept_utilgoal=max(max(self.pre_opponent_utility_log),self.which_pre_accept[1])
                    self.not_accept=1/2.718
                    self.random_max=0
                elif self.which_pre_accept[0]==1: # pre-accept is opponent
                    self.not_accept=0.1
                    self.accept_utilgoal=max(max(self.pre_opponent_utility_log),self.which_pre_accept[1])
            elif self.opponent_strategy==2: # when opponent strategy is others
                if self.which_accept[0]>=0: # pre-negotiation is accepted
                    self.min=min(self.pre_strategy[1]+0.05,0.8)
                else:
                    self.min=max(self.pre_strategy[1]-0.05,0.4)

    def utility_suppose(self,util): # supposed pareto front
        return min(1.0,-float(util)+1.0+float(self.opponent_one))

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
        return "AgentFO2"

    def opponent_action(self, action):
        """Process an action that was received from the opponent.

        Args:
            action (Action): action of opponent
        """
        # if it is an offer, set the last received bid
        if isinstance(action, Offer):

            bid = cast(Offer, action).getBid()
            self.opponent_utility_log.append(self.profile.getUtility(bid))
            count=0
            # ハミング距離
            if len(self.opponent_bid_hamming):
                for issue in self.issue.keys():
                    now_value=bid.getValue(issue)
                    pre_value=self.last_received_bid.getValue(issue)
                    if not now_value==pre_value:
                        count+=1
                self.opponent_bid_hamming.append(count)
            else:
                self.opponent_bid_hamming.append(0)

            # set bid as last received
            self.last_received_bid = bid
            if self.strategy_set_FLAG:
                self.my_strategy_setting()
                self.strategy_set_FLAG=False
        elif isinstance(action,Accept):
            self.which_accept[0]=1
            bid=cast(Accept,action).getBid()
            self.which_accept[1]=self.profile.getUtility(bid)
            if self.strategy_set_FLAG:
                self.which_accept[2]=self.which_accept[1]
            else:
                self.which_accept[2]=self.utility_suppose(self.which_accept[1])

    def my_turn(self):
        """This method is called when it is our turn. It should decide upon an action
        to perform and send this action to the opponent.
        """
        bid = self._makeBid()
        myAction: Action
        if bid == None or (
            self.last_received_bid != None
            and self.accept_condition(bid)
        ):
            # if bid==null we failed to suggest next bid.
            myAction = Accept(self.me, self.last_received_bid)
            self.which_accept[0]=0
            self.which_accept[1]=self.profile.getUtility(self.last_received_bid)
            self.which_accept[2]=self.utility_suppose(self.which_accept[1])
        else:
            myAction = Offer(self.me, bid)
        self.getConnection().send(myAction)

    def save_data(self):
        """This method is called after the negotiation is finished. It can be used to store data
        for learning capabilities. Note that no extensive calculations can be done within this method.
        Taking too much time might result in your agent being killed, so use it for storage only.
        """

        with open(f"{self.storage_dir}/{self.other}.csv", "w") as f:
            writer=csv.writer(f)
            writer.writerow(self.opponent_utility_log)
            writer.writerow(self.opponent_bid_hamming)
            writer.writerow(self.which_accept)
            writer.writerow([self.opponent_strategy,self.min])


    def accept_condition(self, bid: Bid) -> bool:
        if bid is None:
            return False

        # progress of the negotiation session between 0 and 1 (1 is deadline)
        progress = self.progress.get(time() * 1000)

        util=self.profile.getUtility(self.last_received_bid)

        conditions = [
            Decimal(1.02)*util+Decimal(0.04)>self.profile.getUtility(bid),
            util>self.accept_utilgoal and self.not_accept<=progress,
            self.random_max<util and self.not_accept<=progress,
            progress>0.95 and util>=self.utility_suppose(util),
            util>0.85 and self.utility_suppose(util)<=util
        ]

        if self.not_accept>progress:
            if self.random_max<util:
                self.random_max=util

        return any(conditions)


    def _makeBid(self) -> Bid:
        """
        @return next possible bid with current target utility, or null if no such
                bid.
        """
        progress = self.progress.get(time() * 1000)

        utilityGoal = self._getUtilityGoal(
            progress,
            self.getE(),
            self.getMin(),
            self.getMax(),
        )
        
        options: ImmutableList[Bid] = self.allbid.getBids(Interval(utilityGoal-Decimal(0.05),min(self.getMax(),utilityGoal+Decimal(0.05))))
        if options.size() == 0:
            # if we can't find good bid
            options = self.allbid.getBids(Interval(utilityGoal,self.getMax()))
        # pick a random one.
        return options.get(randint(0, options.size() - 1))

    def getE(self) -> float:
        return 0.4

    def getMin(self) -> Decimal:
        return Decimal(self.min)

    def getMax(self) -> Decimal:
        return self.allbid.getRange().getMax()

    def _getUtilityGoal(
        self, t: float, e: float, minUtil: Decimal, maxUtil: Decimal
    ) -> Decimal:
        """
        @param t       the time in [0,1] where 0 means start of nego and 1 the
                       end of nego (absolute time/round limit)
        @param e       the e value that determinses how fast the party makes
                       concessions with time. Typically around 1. 0 means no
                       concession, 1 linear concession, &gt;1 faster than linear
                       concession.
        @param minUtil the minimum utility possible in our profile
        @param maxUtil the maximum utility possible in our profile
        @return the utility goal for this time and e value
        """

        
        ft1 = Decimal(1)
        if e != 0:
            ft1 = round(Decimal(1 - pow(t, 1 / e)), 6)  # defaults ROUND_HALF_UP
        return max(min((minUtil + (maxUtil - minUtil) * ft1), maxUtil), minUtil)


