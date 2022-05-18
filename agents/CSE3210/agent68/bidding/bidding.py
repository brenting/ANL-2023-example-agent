from multiprocessing import Value

from geniusweb.opponentmodel.FrequencyOpponentModel import FrequencyOpponentModel
from geniusweb.profile.Profile import Profile
from geniusweb.issuevalue.Bid import Bid
from geniusweb.profile.utilityspace.LinearAdditive import LinearAdditive
from tudelft.utilities.immutablelist.ImmutableList import ImmutableList
from tudelft.utilities.immutablelist.JoinedList import JoinedList
from geniusweb.inform.Settings import Settings
from geniusweb.profileconnection.ProfileConnectionFactory import (
    ProfileConnectionFactory,
)
from time import sleep, time as clock
from decimal import Decimal

from random import randint, random
from typing import cast, Dict, List, Set, Collection

# from main.bidding.extended_util_space import ExtendedUtilSpace
# from Group68_NegotiationAssignment_Agent.Group68_NegotiationAssignment_Agent.bidding.extended_util_space import ExtendedUtilSpace
from .extended_util_space import ExtendedUtilSpace
from geniusweb.progress.Progress import Progress
import numpy as np


class Bidding():

    def __init__(self) -> None:
        self._profileint: ProfileInterface = None  # type:ignore
        self._utilspace: LinearAdditive = None  # type:ignore
        self._me: PartyId = None  # type:ignore
        self._progress: Progress = None  # type:ignore
        self._extendedspace: ExtendedUtilSpace = None  # type:ignore
        self._e: float = 0.002
        self._settings: Settings = None  # type:ignore

        self._best_backup_bid: Bid = None
        self._opp_utility = None
        self._bids_to_make_stack: [Bid] = []
        self._resBidValue = Decimal('0.0')
        self._recentBidScore = [Decimal('0.0') for _ in range(5)]
        self._utilW = 0.75
        self._leniencyW = 0.25
        self._leniencyBase = 0.35

    def initBidding(self, info: Settings, reporter):
        self._settings = info
        self._me = self._settings.getID()
        self._progress = self._settings.getProgress()
        self._profileint = ProfileConnectionFactory.create(
            self._settings.getProfile().getURI(), reporter
        )
        resBid = self._profileint.getProfile().getReservationBid()
        params = self._settings.getParameters()

        self._utilW = params.getDouble("utilWeight", 0.8, 0.0, 1.0)
        self._leniencyW = params.getDouble("leniencyWeight", 0.2, 0.0, 1.0)
        self._leniencyBase = params.getDouble("leniencyBase", 0.4, 0.0, 1.0)

        if (resBid):
            self._resBidValue = self._profileint.getProfile().getUtility(resBid)
        else:
            self._resBidValue = 0.0

    def updateProgress(self, progress):
        self._progress = progress

    def getE(self) -> float:
        """
        @return the E value that controls the party's behaviour. Depending on the
                value of e, extreme sets show clearly different patterns of
               behaviour [1]:

               1. Boulware: For this strategy e &lt; 1 and the initial offer is
                maintained till time is almost exhausted, when the agent concedes
                up to its reservation value.

                2. Conceder: For this strategy e &gt; 1 and the agent goes to its
                reservation value very quickly.

                3. When e = 1, the price is increased linearly.

                4. When e = 0, the agent plays hardball.
        """
        return self._e

    def receivedBid(self, bid: Bid):
        self._recentBidScore.sort()

        profile = cast(LinearAdditive, self._profileint.getProfile())

        bidUtility = profile.getUtility(bid)

        if (self._recentBidScore[0] < bidUtility):
            self._recentBidScore[0] = bidUtility

        self.updateBestBackupBid(bid, bidUtility)

    def leniencyThresh(self):
        """
        Modify acceptance threshold based on the recent offers from the opponent.
        Good offers -> Lower threshold
        Bad offers -> Higher threshold 

        Returns:
            _type_: _description_
        """
        avgRecentBids = float(sum(self._recentBidScore) / len(self._recentBidScore))

        return np.clip((1 - avgRecentBids) + self._leniencyBase, 0, 1)

    def updateBestBackupBid(self, bid: Bid, bidScore):
        """Updates best bid proposed by the opponent so far.
           In order to have a backup bid in the final few rounds. 

        Args:
            bid (Bid): _description_
        """
        if self._best_backup_bid is None:
            self._best_backup_bid = bid
            return

        profile = cast(LinearAdditive, self._profileint.getProfile())
        if profile.getUtility(self._best_backup_bid) < bidScore:
            self._best_backup_bid = bid

    def updateOpponentUtility(self, oppUtility):
        """Passes the estimated opponent utility function to use during sorting the list of bids gotten

        Args: opp_utility_func: estimated opponent utility function from frequency analysis
        """
        self._opp_utility = oppUtility

    def setProfile(self, profile: Profile):
        self._profileint = profile

    def setE(self, E: float):
        self._e = E

    def _updateUtilSpace(self) -> LinearAdditive:  # throws IOException
        newutilspace = self._profileint.getProfile()
        if not newutilspace == self._utilspace:
            self._utilspace = cast(LinearAdditive, newutilspace)
            self._extendedspace = ExtendedUtilSpace(self._utilspace)
        return self._utilspace

    """Method to select bids to make. Works with stateful stack- _bids_to_make_stack. 
     Makes 2 bids for every utility goal when the stack is empty and pops the stack if it is not. 

           Args: opponent: estimated frequency model of the opponent used to sort and select bids to make
    """

    def makeBid(self, opponent: FrequencyOpponentModel):
        freqs: Dict[str, Dict[Value, int]] = opponent._bidFrequencies

        time = self._progress.get(round(clock() * 1000))

        # if this is the first round of negotiation where the max and second max frequency issue-value are uninitialized.
        # return the max bid from self._extendedspace
        if len(freqs) == 0 or time <= 0.02:
            options = self._extendedspace.getBids(self._extendedspace.getMax())
            outBid = options.get(randint(0, options.size() - 1))

            return outBid

        profile = cast(LinearAdditive, self._profileint.getProfile())
        # Following find largest and second-largest frequency issue-value pairs in one iteration through table
        max_freq = -1
        max_issue: str = None
        max_value: Value = None
        second_max: str = -1
        second_max_issue: Value = None
        second_max_value = None
        for issue in freqs:
            for value in freqs[issue]:
                frequency = freqs[issue][value]
                if frequency >= max_freq:
                    max_issue = issue
                    max_value = value
                    max_freq = frequency
                elif frequency >= second_max:
                    second_max = frequency
                    second_max_value = value
                    second_max_issue = issue

        # Get our bids
        # If we don't have any bids pre-calculated, calculate them
        if len(self._bids_to_make_stack) == 0:
            time = self._progress.get(round(clock() * 1000))
            leniencyValue = self.leniencyThresh()
            utilityGoal = float(self._getUtilityGoal(
                time,
                self.getE(),
                self._extendedspace.getMin(),
                self._extendedspace.getMax(),
            ))

            utilityGoal = Decimal(self._utilW * utilityGoal + self._leniencyW * leniencyValue)

            options: ImmutableList[Bid] = self._extendedspace.getBids(utilityGoal)

            if options.size() == 0:
                # No good bid found - return bid with max utility
                options = self._extendedspace.getBids(self._extendedspace.getMax())
                outBid = options.get(randint(0, options.size() - 1))
                return outBid

            # filter based on the frequencies found above
            filtered = list(filter(lambda bid: bid._issuevalues[max_issue] == max_value, options))
            top = []
            if len(filtered) == 0 or self._progress.get(round(clock() * 1000)) < 0.25:
                util_predictor = lambda bid: opponent.getUtility(bid)

                top = sorted(self._joinedSubList(options, 0, min(10, options.size())), key=util_predictor, reverse=True)
                # if top[0] is smaller than best bid so far
                if profile.getUtility(self._best_backup_bid) >= profile.getUtility(top[0]):
                    self._bids_to_make_stack.append(self._best_backup_bid)
                else:
                    self._bids_to_make_stack.append(top[0])
            else:
                top = filtered[:min(10, len(filtered))]
                util_predictor = lambda bid: opponent.getUtility(bid)
                top = sorted(top, key=util_predictor, reverse=True)

                # Proposing the bid from the opponent with the best utility so far
                if len(top) >= 2:
                    # push two bids on stack if 2 were found else just the one
                    if profile.getUtility(self._best_backup_bid) >= profile.getUtility(top[1]):
                        self._bids_to_make_stack.append(self._best_backup_bid)
                self._bids_to_make_stack.append(top[0])
        # Return the next best calculated bid
        return self._bids_to_make_stack.pop()

    def _pickBestOpponentUtility(self, bidlist: ImmutableList[Bid]) -> List[Bid]:

        outBids: List[Bid] = sorted(bidlist, key=self._opp_utility, reverse=True)

        return outBids[0:2]

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

        # Minimum util value cannot be less than reservation bid value.
        if minUtil < self._resBidValue:
            minUtil = self._resBidValue

        ft1 = Decimal(1)
        if e != 0:
            ft1 = round(Decimal(1 - t * e), 6)  # defaults ROUND_HALF_UP
        return max(min((minUtil + (maxUtil - minUtil) * ft1), maxUtil), minUtil)

    def _isGood(self, bid: Bid) -> bool:
        """
        @param bid the bid to check
        @return true iff bid is good for us according to three criterias mentioned in the report.
        """
        if bid == None or self._profileint == None:
            return False
        profile = cast(LinearAdditive, self._profileint.getProfile())

        time = self._progress.get(round(clock() * 1000))
        
        #Accept final round
        if (time >= 0.99):
            return True

        leniency = self.leniencyThresh()
        bidUtil = profile.getUtility(bid)
        utilGoal = float(self._getUtilityGoal(
            time,
            self.getE(),
            self._extendedspace.getMin(),
            self._extendedspace.getMax(),
        ))

        return bidUtil >= self._resBidValue \
               and bidUtil >= (self._utilW * utilGoal + self._leniencyW * leniency) \
               and bidUtil >= profile.getUtility(self._best_backup_bid)

    def _joinedSubList(self, list: JoinedList, start: int, end: int):
        res = []
        for i in range(start, end):
            res.append(list.get(i))
        return res
