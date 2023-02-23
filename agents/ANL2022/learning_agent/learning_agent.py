import json
import math
import os
from decimal import Decimal
from os.path import exists

from geniusweb.inform.Agreements import Agreements
from geniusweb.issuevalue.ValueSet import ValueSet
from geniusweb.issuevalue.Value import Value
from geniusweb.issuevalue.DiscreteValue import DiscreteValue
from geniusweb.issuevalue.NumberValue import NumberValue

import logging
from random import randint
import time
from typing import cast

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
from geniusweb.profile.utilityspace.UtilitySpace import UtilitySpace
from geniusweb.profileconnection.ProfileConnectionFactory import (
    ProfileConnectionFactory,
)
from geniusweb.progress.ProgressTime import ProgressTime
from geniusweb.references.Parameters import Parameters
from numpy import long
from tudelft_utilities_logging.ReportToLogger import ReportToLogger

from .LearnedData import LearnedData
from .NegotiationData import NegotiationData
from .Pair import Pair

# static vars
defualtAlpha: float = 10.7
# estimate opponent time - variant threshold function
tSplit: int = 40
# agent has 2 - phases - learning of the opponent and offering bids while considering opponent utility, this constant define the threshold between those two phases
tPhase: float = 0.2



class LearningAgent(DefaultParty):
    def __init__(self):
        super().__init__()
        self.logger: ReportToLogger = self.getReporter()
        self.lastReceivedBid: Bid = None
        self.me: PartyId = None
        self.progress: ProgressTime = None
        self.protocol: str = None
        self.parameters: Parameters = None
        self.utilitySpace: UtilitySpace = None
        self.domain: Domain = None
        self.learnedData: LearnedData = None
        self.negotiationData: NegotiationData = None
        self.learnedDataPath: str = None
        self.negotiationDataPath: str = None
        self.storage_dir: str = None

        self.opponentName: str = None

        # Expecting Lower Limit of Concession Function behavior
        # The idea here that we will keep for a negotiation scenario the most frequent
        # Issues - Values, afterwards, as a counter offer bid for each issue we will select the most frequent value.
        self.freqMap: dict = None

        # average and standard deviation of the competition for determine "good" utility threshold
        self.avgUtil: float = 0.95
        self.stdUtil: float = 0.15
        self.utilThreshold: float = 0.95

        self.alpha: float = defualtAlpha

        self.opCounter: list = [0] * tSplit
        self.opSum: list = [0.0] * tSplit
        self.opThreshold: list = [0.0] * tSplit
        self.opReject: list = [0.0] * tSplit

        # Best bid for agent, exists if bid space is small enough to search in
        self.MAX_SEARCHABLE_BIDSPACE: long = 50000
        self.MIN_UTILITY: float = 0.6
        self.optimalBid: Bid = None
        self.bestOfferBid: Bid = None
        self.allBidList: AllBidsList = None

        self.lastOfferBid = None  # our last offer to the opponent

    def notifyChange(self, data: Inform):
        """
                Args:
                    data (Inform): Contains either a request for action or information.
                """
        try:
            # a Settings message is the first message that will be send to your
            # agent containing all the information about the negotiation session.
            if isinstance(data, Settings):
                self.settingsFunction(cast(Settings, data))

            # ActionDone informs you of an action (an offer or an accept)
            # that is performed by one of the agents (including yourself).
            elif isinstance(data, ActionDone):
                self.actionDoneFunction(cast(ActionDone, data))

            # YourTurn notifies you that it is your turn to act
            elif isinstance(data, YourTurn):
                # execute a turn
                self.myTurn()

            # Finished will be send if the negotiation has ended (through agreement or deadline)
            elif isinstance(data, Finished):
                self.finishedFunction(cast(Finished, data))

            else:
                self.logger.log(logging.WARNING, "Ignoring unknown info " + str(data))

        except:
            self.logger.log(logging.ERROR, "error notifyChange")

    def getDescription(self) -> str:
        """Returns a description of your agent.

        Returns:
            str: Agent description
        """
        return "This is party of ANL 2022. It can handle the Learn protocol and learns utility function and threshold of the opponent."

    def getCapabilities(self) -> Capabilities:
        """
        Method to indicate to the protocol what the capabilities of this agent are.
        Leave it as is for the ANL 2022 competition

        Returns:
            Capabilities: Capabilities representation class
        """
        return Capabilities(
            set(["SAOP"]),
            set(["geniusweb.profile.utilityspace.LinearAdditive"]),
        )

    def finishedFunction(self, data: Finished):
        # object also contains the final agreement( if any).
        agreements: Agreements = data.getAgreements()
        self.processAgreements(agreements)

        # Write the negotiation data that we collected to the path provided.
        if not (self.negotiationDataPath == None or self.negotiationData == None):
            try:
                with open(self.negotiationDataPath, "w") as f:
                    # w means overwritten
                    json.dump(self.negotiationData.__dict__, default=lambda o: o.__dict__, indent=5, fp=f)


            except:
                self.logger.log(logging.ERROR, "Failed to write negotiation data to disk")

        # Write the learned data to the path provided.
        if not (self.learnedDataPath == None or self.learnedData == None):
            try:
                with open(self.learnedDataPath, "w") as f:
                    # w means overwritten
                    json.dump(self.learnedData.__dict__, default=lambda o: o.__dict__, indent=9, fp=f)


            except:
                self.logger.log(logging.ERROR, "Failed to learned data to disk")

        self.logger.log(logging.INFO, "party is terminating:")
        super().terminate()

    def actionDoneFunction(self, data: ActionDone):
        # The info object is an action that is performed by an agent.
        action: Action = data.getAction()
        actor = action.getActor()

        # Check if this is not our own action
        if self.me is not None and not (self.me == actor):
            # Check if we already know who we are playing against.
            if self.opponentName == None:
                # The part behind the last _ is always changing, so we must cut it off.
                self.opponentName = str(actor).rsplit("_", 1)[0]

                # path depend on opponent name
                self.negotiationDataPath = self.getPath("negotiationData", self.opponentName)
                self.learnedDataPath = self.getPath("learnedData", self.opponentName)

                # update and load learnedData
                self.updateAndLoadLearnedData()

                # Add name of the opponent to the negotiation data
                self.negotiationData.setOpponentName(self.opponentName)

                # avg opponent offer utility
                self.opThreshold = self.learnedData.getSmoothThresholdOverTime() \
                    if self.learnedData != None else None
                if not (self.opThreshold == None):
                    for i in range(tSplit):
                        self.opThreshold[i] = self.opThreshold[i] if self.opThreshold[i] > 0 else self.opThreshold[
                            i - 1]

                # max offer the opponent reject
                self.opReject = self.learnedData.getSmoothRejectOverTime() \
                    if self.learnedData != None else None
                if not (self.opReject == None):
                    for i in range(tSplit):
                        self.opReject[i] = self.opReject[i] if self.opReject[i] > 0 else self.opReject[
                            i - 1]

                # decay rate of threshold function
                self.alpha = self.learnedData.getOpponentAlpha() if self.learnedData != None else 0.0
                self.alpha = self.alpha if self.alpha > 0.0 else defualtAlpha

            # Process the action of the opponent.
            self.processAction(action)

    def settingsFunction(self, data: Settings):
        # info is a Settings object that is passed at the start of a negotiation
        settings: Settings = data

        # ID of my agent
        self.me = settings.getID()

        # The progress object keeps track of the deadline
        self.progress = settings.getProgress()

        # Protocol that is initiate for the agent
        self.protocol = str(settings.getProtocol().getURI().getPath())

        # Parameters for the agent (can be passed through the GeniusWeb GUI, or a JSON-file)
        self.parameters = settings.getParameters()

        self.storage_dir = self.parameters.get("storage_dir")

        # We are in the negotiation step.
        # Create a new NegotiationData object to store information on this negotiation.
        # See 'NegotiationData.py'.

        self.negotiationData = NegotiationData()

        # Obtain our utility space, i.e.the problem we are negotiating and our
        # preferences over it.
        try:
            # the profile contains the preferences of the agent over the domain
            profile_connection = ProfileConnectionFactory.create(data.getProfile().getURI(), self.getReporter())
            self.domain = profile_connection.getProfile().getDomain()

            # Create a Issues-Values frequency map
            if self.freqMap == None:
                # Map wasn't created before, create a new instance now
                self.freqMap = {}
            else:
                # Map was created before, but this is a new negotiation scenario, clear the old map.
                self.freqMap.clear()

            # Obtain all of the issues in the current negotiation domain
            issues: set = self.domain.getIssues()
            for s in issues:
                # create new list of all the values for
                p: Pair = Pair()
                p.vList = {}

                # gather type of issue based on the first element
                vs: ValueSet = self.domain.getValues(s)
                if isinstance(vs.get(0), DiscreteValue):
                    p.type = 0
                elif isinstance(vs.get(0), NumberValue):
                    p.type = 1

                # Obtain all of the values for an issue "s"
                for v in vs:
                    # Add a new entry in the frequency map for each(s, v, typeof(v))
                    vStr: str = self.valueToStr(v, p)
                    p.vList[vStr] = 0

                self.freqMap[s] = p

        except:
            self.logger.log(logging.ERROR, "error settingsFunction")

        # self.utilitySpace = cast(profile_connection.getProfile(), UtilitySpace)
        self.utilitySpace = profile_connection.getProfile()
        profile_connection.close()

        self.allBidList = AllBidsList(self.domain)

        # Attempt to find the optimal bid in a search-able bid space, if bid space size
        # is small / equal to MAX_SEARCHABLE_BIDSPACE
        if self.allBidList.size() <= self.MAX_SEARCHABLE_BIDSPACE:
            mx_util: Decimal = Decimal(0)
            for i in range(self.allBidList.size()):
                b: Bid = self.allBidList.get(i)
                canidate: Decimal = self.utilitySpace.getUtility(b)
                if canidate > mx_util:
                    mx_util = canidate
                    self.optimalBid = b

        else:
            mx_util: Decimal = Decimal(0)
            # Iterate randomly through list of bids until we find a good bid
            for attempt in range(self.MAX_SEARCHABLE_BIDSPACE.intValue()):
                i: long = randint(0, self.allBidList.size())
                b: Bid = self.allBidList.get(i)
                canidate: Decimal = self.utilitySpace.getUtility(b)
                if canidate > mx_util:
                    mx_util = canidate
                    self.optimalBid = b

    def isNearNegotiationEnd(self):
        return 0 if self.progress.get(int(time.time() * 1000)) < tPhase else 1

    def processAction(self, action: Action):
        """Processes an Action performed by the opponent."""
        if isinstance(action, Offer):
            # If the action was an offer: Obtain the bid
            self.lastReceivedBid = cast(Offer, action).getBid()
            self.updateFreqMap(self.lastReceivedBid)

            # add it's value to our negotiation data.
            utilVal: float = float(self.utilitySpace.getUtility(self.lastReceivedBid))
            self.negotiationData.addBidUtil(utilVal)

    def processAgreements(self, agreements: Agreements):

        """ This method is called when the negotiation has finished. It can process the"
              final agreement.
         """
        # Check if we reached an agreement (walking away or passing the deadline
        # results in no agreement)
        if agreements.getMap() != None and not (agreements.getMap() == {}):
            # Get the bid that is agreed upon and add it's value to our negotiation data
            agreement: Bid = list(agreements.getMap().values())[0]
            self.negotiationData.addAgreementUtil(float(self.utilitySpace.getUtility(agreement)))
            self.negotiationData.setOpponentUtil(self.calcOpValue(agreement))

        # negotiation failed
        else:
            if not (self.bestOfferBid == None):
                self.negotiationData.addAgreementUtil(float(self.utilitySpace.getUtility(self.bestOfferBid)))

            # update opponent reject list
            if self.lastOfferBid != None:
                self.negotiationData.addRejectUtil(tSplit - 1, self.calcOpValue(self.lastOfferBid))

        # update the opponent offers map, regardless of achieving agreement or not
        try:
            self.negotiationData.updateOpponentOffers(self.opSum, self.opCounter);
        except:
            self.logger.log(logging.ERROR, "error processAgreements")

    # send our next offer
    def myTurn(self):
        action: Action = None

        # save average of the last avgSplit offers (only when frequency table is stabilized)
        if self.isNearNegotiationEnd() > 0:
            index: int = (int)((tSplit - 1) / (1 - tPhase) * (self.progress.get(int(time.time() * 1000)) - tPhase))

            if self.lastReceivedBid != None:
                self.opSum[index] += self.calcOpValue(self.lastReceivedBid)
                self.opCounter[index] += 1

            if self.lastOfferBid != None:
                self.negotiationData.addRejectUtil(index, self.calcOpValue(self.lastOfferBid))

            # evaluate the offer and accept or give counter-offer
        if self.isGood(self.lastReceivedBid):
            # If the last received bid is good: create Accept action
            action = Accept(self.me, self.lastReceivedBid)
        else:
            # there are 3 phases in the negotiation process:
            # 1. Send random bids that considered to be GOOD for our agent
            # 2. Send random bids that considered to be GOOD for both of the agents
            bid: Bid = None

            if self.bestOfferBid == None:
                self.bestOfferBid = self.lastReceivedBid
            elif self.lastReceivedBid != None and self.utilitySpace.getUtility(self.lastReceivedBid) > self.utilitySpace \
                    .getUtility(self.bestOfferBid):
                self.bestOfferBid = self.lastReceivedBid

            isNearNegotiationEnd = self.isNearNegotiationEnd()
            if isNearNegotiationEnd == 0:
                attempt = 0
                while attempt < 1000 and not self.isGood(bid):
                    attempt += 1
                    i: long = randint(0, self.allBidList.size())
                    bid = self.allBidList.get(i)

                bid = bid if (self.isGood(
                    bid)) else self.optimalBid  # if the last bid isn't good, offer (default) the optimal bid

            elif isNearNegotiationEnd == 1:
                if self.progress.get(int(time.time() * 1000)) > 0.95:
                    maxOpponentUtility: float = 0.0
                    maxBid: Bid = None
                    i = 0
                    while i < 10000 and self.progress.get(int(time.time() * 1000)) < 0.99:
                        i: long = randint(0, self.allBidList.size())
                        bid = self.allBidList.get(i)
                        if self.isGood(bid) and self.isOpGood(bid):
                            opValue = self.calcOpValue(bid)
                            if opValue > maxOpponentUtility:
                                maxOpponentUtility = opValue
                                maxBid = bid
                        i += 1
                    bid = maxBid
                else:
                    # look for bid with max utility for opponent
                    maxOpponentUtility: float = 0.0
                    maxBid: Bid = None
                    for i in range(2000):
                        i: long = randint(0, self.allBidList.size())
                        bid = self.allBidList.get(i)
                        if self.isGood(bid) and self.isOpGood(bid):
                            opValue = self.calcOpValue(bid)
                            if opValue > maxOpponentUtility:
                                maxOpponentUtility = opValue
                                maxBid = bid
                    bid = maxBid

                bid = self.bestOfferBid if (self.progress.get(int(time.time() * 1000)) > 0.99) and self.isGood(
                    self.bestOfferBid) else bid
                bid = bid if self.isGood(
                    bid) else self.optimalBid  # if the last bid isn't good, offer (default) the optimal bid

            # Create offer action
            action = Offer(self.me, bid)
            self.lastOfferBid = bid

        # Send action
        self.getConnection().send(action)

    def isGood(self, bid: Bid):
        """ The method checks if a bid is good.
          param bid the bid to check
          return true iff bid is good for us.
          """
        if bid == None:
            return False
        maxVlue: float = 0.95 * float(
            self.utilitySpace.getUtility(self.optimalBid)) if not self.optimalBid == None else 0.95
        avgMaxUtility: float = self.learnedData.getAvgMaxUtility() \
            if self.learnedData != None \
            else self.avgUtil

        self.utilThreshold = maxVlue \
                             - (maxVlue - 0.55 * self.avgUtil - 0.4 * avgMaxUtility + 0.5 * pow(self.stdUtil, 2)) \
                             * (math.exp(self.alpha * self.progress.get(int(time.time() * 1000))) - 1) \
                             / (math.exp(self.alpha) - 1)

        if (self.utilThreshold < self.MIN_UTILITY):
            self.utilThreshold = self.MIN_UTILITY

        return float(self.utilitySpace.getUtility(bid)) >= self.utilThreshold

    def calcOpValue(self, bid: Bid):
        value: float = 0

        issues = bid.getIssues()
        valUtil: list = [0] * len(issues)
        issWeght: list = [0] * len(issues)
        k: int = 0  # index

        for s in issues:
            p: Pair = self.freqMap[s]
            v: Value = bid.getValue(s)
            vs: str = self.valueToStr(v, p)

            # calculate utility of value (in the issue)
            sumOfValues: int = 0
            maxValue: int = 1
            for vString in p.vList.keys():
                sumOfValues += p.vList[vString]
                maxValue = max(maxValue, p.vList[vString])

            # calculate estimated utility of the issuevalue
            valUtil[k] = p.vList.get(vs) / maxValue

            # calculate the inverse std deviation of the array
            mean: float = sumOfValues / len(p.vList)
            for vString in p.vList.keys():
                issWeght[k] += pow(p.vList.get(vString) - mean, 2)
            issWeght[k] = 1.0 / math.sqrt((issWeght[k] + 0.1) / len(p.vList))

            k += 1

        sumOfWght: float = 0
        for k in range(len(issues)):
            value += valUtil[k] * issWeght[k]
            sumOfWght += issWeght[k]

        return value / sumOfWght

    def isOpGood(self, bid: Bid):
        if bid == None:
            return False

        value: float = self.calcOpValue(bid)
        index: int = int(((tSplit - 1) / (1 - tPhase) * (self.progress.get(int(
            time.time() * 1000)) - tPhase)))
        # change
        opThreshold: float = max(max(2 * self.opThreshold[index] - 1, self.opReject[index]),
                                 0.2) if self.opThreshold != None and self.opReject != None else 0.6
        return value > opThreshold

    def updateFreqMap(self, bid: Bid):
        if not (bid == None):
            issues = bid.getIssues()

            for s in issues:
                p: Pair = self.freqMap.get(s)
                v: Value = bid.getValue(s)

                vs: str = self.valueToStr(v, p)
                p.vList[vs] = (p.vList.get(vs) + 1)

    def valueToStr(self, v: Value, p: Pair):
        v_str: str = ""
        if p.type == 0:
            v_str = cast(DiscreteValue, v).getValue()
        elif p.type == 1:
            v_str = cast(NumberValue, v).getValue()

        if v_str == "":
            print("Warning: Value wasn't found")
        return v_str

    def getPath(self, dataType: str, opponentName: str):
        return os.path.join(self.storage_dir, dataType + "_" + opponentName + ".json")

    def updateAndLoadLearnedData(self):
        # we didn't meet this opponent before
        if exists(self.negotiationDataPath):
            try:
                # Load the negotiation data object of a previous negotiation
                with open(self.negotiationDataPath, "r") as f:
                    negotiationData: NegotiationData = NegotiationData()
                    negotiationData.encode(list(json.load(f).values()))

            except:
                self.logger.log(logging.ERROR, "Negotiation data does not exist")

            if exists(self.learnedDataPath):
                try:
                    # Load the negotiation data object of a previous negotiation
                    with open(self.learnedDataPath, "r") as f:
                        self.learnedData = LearnedData()
                        self.learnedData.encode(list(json.load(f).values()))

                except:
                    self.logger.log(logging.ERROR, "learned data does not exist")

            else:
                self.learnedData = LearnedData()

            # Process the negotiation data in our learned Data
            self.learnedData.update(negotiationData)
            self.avgUtil = self.learnedData.getAvgUtility()
            self.stdUtil = self.learnedData.getStdUtility()
