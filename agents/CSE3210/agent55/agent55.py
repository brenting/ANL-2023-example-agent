import logging
import time
from random import randint, uniform
from typing import cast
from math import log10, floor
from geniusweb.actions.Accept import Accept
from geniusweb.actions.Action import Action
from geniusweb.actions.Offer import Offer
from geniusweb.bidspace.AllBidsList import AllBidsList
from geniusweb.bidspace.BidsWithUtility import BidsWithUtility
from geniusweb.profile.utilityspace.LinearAdditive import LinearAdditive
from geniusweb.bidspace.Interval import Interval
from geniusweb.inform.ActionDone import ActionDone
from geniusweb.inform.Finished import Finished
from geniusweb.inform.Inform import Inform
from geniusweb.inform.Settings import Settings
from geniusweb.inform.YourTurn import YourTurn
from geniusweb.issuevalue.Bid import Bid
from geniusweb.party.Capabilities import Capabilities
from geniusweb.party.DefaultParty import DefaultParty
from geniusweb.profileconnection.ProfileConnectionFactory import ProfileConnectionFactory
from geniusweb.progress.ProgressRounds import ProgressRounds
from tudelft_utilities_logging.Reporter import Reporter
import heapq
from decimal import *
from .Group55OpponentModel import FrequencyOpponentModel


class Agent55(DefaultParty):
    """
    Template agent that offers random bids until a bid with sufficient utility is offered.
    """

    def __init__(self, reporter: Reporter = None):
        super().__init__(reporter)
        self._utilspace: LinearAdditive = None
        self._bidutils = None
        self.getReporter().log(logging.INFO, "party is initialized")
        self._profile = None
        self._lastReceivedBid: Bid = None

        """
        this will create the opponent model
        """
        self.opponentModel = FrequencyOpponentModel.create()

        """
        baselineAcceptableUtility is a utility value for which we accept immediately
        """
        self.baselineAcceptableUtility = 0.95

        """
        hardballOpponentUtilityDelta is the opponent utility change value over which an opponnent is considered to be playing hardball
        """
        self.hardballOpponentUtilityDelta = -0.005

        """
        timePassedAccept is a fixed amount of time passed in the negotiation after which we accept
        """
        self.timePassedAccept = 0.95

        """
        timePassedConcede is a fixed amount of time passed in the negotiation when our agent starts conceding more
        """
        self.timePassedConcede = 0.75

        """
        These two variables will show the average utility-change of their and our agent, throughout their offerings.
        This excludes the jump from no offer to the initial offer. Note that the first bid this will return None, so
        there must be a check for this.
        """
        self.theirAverageUtilityChangeByTheirBids = None
        self.ourAverageUtilityChangeByTheirBids = None

        """
        These variables help with the calculation of 'theirAverageUtilityChangeByTheirBids' and
        'ourAverageUtilityChangeByTheirBids'.
        """
        self.sumChangeOurUtilitiesByTheirBids = 0
        self.sumChangeTheirUtilitiesByTheirBids = 0
        self.ourUtilityLastTimeByTheirBids = 0
        self.theirUtilityLastTimeByTheirBids = 0

        """
        Matas: These variables enable our bidding strategy
        """
        self.ourBestBids = []
        self.opponentsBestBids = []
        self.roundsSinceBidRecalibration = 0
        self.reCalibrateEveryRounds = 10
        self.randomBidDiscoveryAttemptsPerTurn = 500
        self.acceptableUtilityNormalizationWidth = 0.1
        self.utilityThresholdAdjustmentStep = 0.1
        self.percentOfTimeWeUseOpponentsBestBidIfItIsBetter = 0.7
        self.paddingForUsingRandomBid = 0.1
        self.amountOfBestBidsToKeep = 50
        self.bidsToKeepBasedOnProgressScale = 0.3
        self.opponentNicenessConceedingContributionScale = 0.3

    def notifyChange(self, info: Inform):
        """This is the entry point of all interaction with your agent after is has been initialised.

        Args:
            info (Inform): Contains either a request for action or information.
        """

        # a Settings message is the first message that will be send to your
        # agent containing all the information about the negotiation session.
        if isinstance(info, Settings):
            self._settings: Settings = cast(Settings, info)
            self._me = self._settings.getID()

            # progress towards the deadline has to be tracked manually through the use of the Progress object
            self._progress: ProgressRounds = self._settings.getProgress()

            # the profile contains the preferences of the agent over the domain
            self._profile = ProfileConnectionFactory.create(
                info.getProfile().getURI(), self.getReporter()
            )

            # create and initialize opponent-model
            profile = self._profile.getProfile()
            self.opponentModel = self.opponentModel.With(
                profile.getDomain(), profile.getReservationBid())

        # ActionDone is an action send by an opponent (an offer or an accept)
        elif isinstance(info, ActionDone):
            action: Action = cast(ActionDone, info).getAction()

            # if it is an offer, set the last received bid
            if isinstance(action, Offer):
                self._lastReceivedBid = cast(Offer, action).getBid()

                """
                Important caveat: anytime we do an offer the program also passes this part and updates the
                last_received bid with the offer we made.

                The reason that their variable is called 'lastReceivedBid' is that we access it during our turn and
                during our turn this is always the last bid done by the opponent.

                For this reason, we first check if the Action does not contain our id before updating the
                opponent model.
                """
                if cast(Offer, action).getActor() is not self._me:
                    self.opponentModel = self.opponentModel.WithAction(
                        action, self._progress)
                    self._updateOpponentModel()

        # YourTurn notifies you that it is your turn to act
        elif isinstance(info, YourTurn):
            action = self._myTurn()
            if isinstance(self._progress, ProgressRounds):
                self._progress = self._progress.advance()
            self.getConnection().send(action)

        # Finished will be send if the negotiation has ended (through agreement or deadline)
        elif isinstance(info, Finished):
            # terminate the agent MUST BE CALLED
            self.terminate()
        else:
            self.getReporter().log(
                logging.WARNING, "Ignoring unknown info " + str(info)
            )

    # lets the geniusweb system know what settings this agent can handle
    # leave it as it is for this competition
    def getCapabilities(self) -> Capabilities:
        return Capabilities(
            set(["SAOP"]),
            set(["geniusweb.profile.utilityspace.LinearAdditive"]),
        )

    # terminates the agent and its connections
    # leave it as it is for this competition
    def terminate(self):
        self.getReporter().log(logging.INFO, "party is terminating:")
        super().terminate()
        if self._profile is not None:
            self._profile.close()
            self._profile = None

    

    # give a description of your agent

    def getDescription(self) -> str:
        return "Agent55"

    # execute a turn
    def _myTurn(self):
        self._updateUtilSpace()

        # Generate a bid according to our current acceptable utility
        (aGoodBid, nashProduct) = self._generateAGoodBid()

        # Update our best bid store and fetch the best bid
        (currentBestOurBid, currentBestOurBidNashProduct) = self._updateBidsAndGetBestBid(
            self.ourBestBids, aGoodBid, nashProduct, floor(self.amountOfBestBidsToKeep * (1 - self._progress.get(time.time() * 1000)) * self.bidsToKeepBasedOnProgressScale))

        currentBestBid = currentBestOurBid
        currentBestBidNashProduct = currentBestOurBidNashProduct

        # If we have a bid from the opponent, store it in the opponent's best bid store
        (currentBestTheirBid, currentBestTheirBidNashProduct) = (None, 0)
        if self._lastReceivedBid is not None:
            (currentBestTheirBid, currentBestTheirBidNashProduct) = self._updateBidsAndGetBestBid(
                self.opponentsBestBids, self._lastReceivedBid, self._getNashProduct(self._lastReceivedBid), 1)

        # print("Our best stored bid: {}, their best stored bid: {}".format(
        #     currentBestOurBidNashProduct,  currentBestTheirBidNashProduct))

        # Pick which best bid we are using as base. Slight random bias towards our best bid. Also the opponent best bid must be more favorable to us.
        if currentBestOurBidNashProduct < currentBestTheirBidNashProduct \
                and self.percentOfTimeWeUseOpponentsBestBidIfItIsBetter > uniform(0, 1) \
                and self._profile.getProfile().getUtility(currentBestTheirBid) > self.opponentModel.getUtility(currentBestTheirBid):

            currentBestBid = currentBestTheirBid
            currentBestBidNashProduct = currentBestTheirBidNashProduct

        # Use a newly generated bid instead of offering an optimal one with a random chance that is higher at the beginning and lower at the end.
        # Moreover, use the freshly generated bids if we are conceding.
        if currentBestBid is None or self._progress.get(time.time() * 1000) + self.paddingForUsingRandomBid < uniform(0, 1) or self._progress.get(time.time() * 1000) > self.timePassedConcede:
            currentBestBid = aGoodBid
            currentBestBidNashProduct = nashProduct

        if self._isAcceptable(self._lastReceivedBid, currentBestBid):
            # if so, accept the offer
            action = Accept(self._me, self._lastReceivedBid)
        else:
            # if not, propose a counter offer

            action = Offer(self._me, currentBestBid)

        # send the action
        return action

    def _isOpponentPlayingHardball(self) -> bool:
        if self.theirAverageUtilityChangeByTheirBids is None:
            return False

        return self.theirAverageUtilityChangeByTheirBids > self.hardballOpponentUtilityDelta

    def _getHardballFactor(self) -> Decimal:
        timeLeft = self._progress.get(time.time() * 1000)

        # high hardball factor before conceding time
        if timeLeft <= self.timePassedConcede:
            return 20

        # opponent is not playing hardball so we can concede less
        if not self._isOpponentPlayingHardball():
            return 14

        return 8

    def _getAcceptableUtility(self) -> Decimal:
        timePassed = self._progress.get(time.time() * 1000)
        timeLeft = 1 - timePassed
        # the higher the factor the less we concede
        hardballFactor = self._getHardballFactor()

        return Decimal(log10(timeLeft) / hardballFactor + self.baselineAcceptableUtility)

    # method that checks if we should accept an offer
    def _isAcceptable(self, lastReceivedBid: Bid, proposedBid: Bid) -> bool:
        if lastReceivedBid is None or proposedBid is None:
            return False

        profile = self._profile.getProfile()

        if profile.getUtility(lastReceivedBid) >= profile.getUtility(proposedBid):
            return True

        return self._isGood(lastReceivedBid)

    # method that checks if an offer is considered good
    def _isGood(self, lastReceivedBid: Bid) -> bool:
        if lastReceivedBid is None:
            return False

        progress = self._progress.get(time.time() * 1000)

        if progress >= self.timePassedAccept:
            return True

        profile = self._profile.getProfile()
        utility = profile.getUtility(lastReceivedBid)

        if utility >= self.baselineAcceptableUtility:
            return True

        return utility >= self._getAcceptableUtility()

    def _generateAGoodBid(self) -> tuple[Bid, Decimal]:
        # Use the expexted opponent utility to set a range to find a bid that is acceptable to us

        # Starting points
        acceptableUtility = self._getAcceptableUtility()
        maxUtility = 1

        # Decrease our max utility if the opponent is taking losses according to our model
        if self._progress.get(time.time() * 1000) > self.timePassedConcede:
            maxUtility -= (Decimal(self._progress.get(time.time() * 1000)) *
                           Decimal(self.opponentNicenessConceedingContributionScale) * (1 - self.theirUtilityLastTimeByTheirBids))

        # Normalize in case we decrease maxUtil by too much.
        if maxUtility <= acceptableUtility:
            acceptableUtility = maxUtility - \
                Decimal(self.acceptableUtilityNormalizationWidth)

        # Attempt to generate a bid, and adjust our utility thresholds if necessary
        while maxUtility <= 1 or acceptableUtility >= 0:
            generatedBid, nash = self._generateAGoodBidGivenMinMaxUtil(
                acceptableUtility, maxUtility)
            if generatedBid is None:

                # Adjust thresholds. First expand the max utility, then reduce the min utility.
                if maxUtility < 1:
                    maxUtility = min(
                        maxUtility + Decimal(self.utilityThresholdAdjustmentStep), 1)
                else:
                    acceptableUtility = max(
                        acceptableUtility - Decimal(self.utilityThresholdAdjustmentStep), 0)

            else:
                return generatedBid, nash

        # All atempts have failed. Generate a random bid.
        return self._generateRandomBid()

    def _generateAGoodBidGivenMinMaxUtil(self, acceptableUtility, maxUtility) -> tuple[Bid, Decimal]:
        currentAvailableBids = self._bidutils.getBids(
            Interval(acceptableUtility, Decimal(maxUtility))
        )

        # If no available bids, we can't generate a bid.
        if currentAvailableBids.size() == 0:
            return None, 0

        goodBid = currentAvailableBids.get(
            randint(0, currentAvailableBids.size() - 1))
        nash = self._getNashProduct(goodBid)

        return goodBid, nash

    def _updateBidsAndGetBestBid(self, bestBids, bestBidFromThisTurn, nashProduct, nBestBids) -> Bid:
        self.roundsSinceBidRecalibration += 1

        # Must at least pick one option
        if nBestBids < 1:
            nBestBids = 1

        # After a certain amount of rounds has passed, we recallibrate our bid storage
        if self.roundsSinceBidRecalibration >= self.reCalibrateEveryRounds:
            self.roundsSinceBidRecalibration = 0

            # Update and prune
            updatedRaw = [self._popAndUpdate(bestBids)
                          for i in range(min(len(bestBids), self.amountOfBestBidsToKeep))]

            bestBids.clear()
            [heapq.heappush(bestBids, x)
             for x in updatedRaw]

        # Invert the nash product since heapq is a min queue
        invertedNashProduct = 1 - nashProduct
        heapq.heappush(bestBids,
                       (invertedNashProduct, MaxHeapObj(bestBidFromThisTurn)))

        # Pick a bid close to the Nash Equilibrium
        toPickFrom = heapq.nsmallest(min(nBestBids, len(bestBids)), bestBids)

        (currentBestInvertedNashProduct,
         currentBestBid) = toPickFrom[randint(0, len(toPickFrom) - 1)]

        # Invert nash product and return
        return currentBestBid.val, 1 - currentBestInvertedNashProduct

    def _getNashProduct(self, bid) -> Decimal:
        utility = self._profile.getProfile().getUtility(bid)
        opponentUtility = self.opponentModel.getUtility(bid)
        return utility * opponentUtility

    def _popAndUpdate(self, bestBids):
        x = heapq.heappop(bestBids)
        return (self._getNashProduct(x[1].val), x[1])

    def _updateUtilSpace(self) -> LinearAdditive:
        newutilspace = self._profile.getProfile()
        if not newutilspace == self._utilspace:
            self._utilspace = newutilspace
            self._bidutils = BidsWithUtility.create(self._utilspace)
        return self._utilspace

    def _generateRandomBid(self) -> tuple[Bid, Decimal]:
        domain = self._profile.getProfile().getDomain()
        all_bids = AllBidsList(domain)
        bid = None

        # Try to generate a good random bid
        for _ in range(self.randomBidDiscoveryAttemptsPerTurn):
            candidate = all_bids.get(randint(0, all_bids.size() - 1))
            if self._isGood(candidate):
                bid = candidate
                break

        # If no good ones found within the allocated attempt count, pick at random
        if bid is None:
            bid = all_bids.get(randint(0, all_bids.size() - 1))

        nash = self._getNashProduct(bid)

        return bid, nash

    """
    This method maintains all extensions of the opponent model. Everytime the opponent makes an offer, this gets
    updated. Currently the method maintains the following extensions:
    * theirAverageUtilityChangeByTheirBids
    * ourAverageUtilityChangeByTheirBids
    """

    def _updateOpponentModel(self):

        ###This block calculates: ourAverageUtilityChangeByTheirBids and TheirAverageUtilityChangeByTheirBids ########

        ourUtilityThisBid = self._profile.getProfile().getUtility(self._lastReceivedBid)
        theirUtilityThisBid = self.opponentModel.getUtility(
            self._lastReceivedBid)
        bidCount = self.opponentModel._totalBids

        # if it's the first offer
        if bidCount == 1:
            self.ourUtilityLastTimeByTheirBids = ourUtilityThisBid
            self.theirUtilityLastTimeByTheirBids = theirUtilityThisBid
        else:
            ourDifference = ourUtilityThisBid - self.ourUtilityLastTimeByTheirBids
            theirDifference = theirUtilityThisBid - self.theirUtilityLastTimeByTheirBids

            self.sumChangeOurUtilitiesByTheirBids += ourDifference
            self.sumChangeTheirUtilitiesByTheirBids += theirDifference

            self.theirAverageUtilityChangeByTheirBids = self.sumChangeTheirUtilitiesByTheirBids / \
                (bidCount - 1)
            self.ourAverageUtilityChangeByTheirBids = self.sumChangeOurUtilitiesByTheirBids / \
                (bidCount - 1)

            self.ourUtilityLastTimeByTheirBids = ourUtilityThisBid
            self.theirUtilityLastTimeByTheirBids = theirUtilityThisBid
            ###End of calculation: ourAverageUtilityChangeByTheirBids and TheirAverageUtilityChangeByTheirBids ########

# helper for heap


class MaxHeapObj(object):
    def __init__(self, val): self.val = val
    def __lt__(self, other): return True
    def __eq__(self, other): return True
