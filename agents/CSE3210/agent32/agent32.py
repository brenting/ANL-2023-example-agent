import logging
import time
from random import randint
from typing import cast
import numpy as np

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
from geniusweb.issuevalue.Value import Value
from geniusweb.issuevalue.ValueSet import ValueSet
from geniusweb.party.Capabilities import Capabilities
from geniusweb.party.DefaultParty import DefaultParty
from geniusweb.profile.utilityspace.UtilitySpace import UtilitySpace
from geniusweb.profileconnection.ProfileConnectionFactory import (
    ProfileConnectionFactory,
)
from geniusweb.progress.ProgressRounds import ProgressRounds
from tudelft_utilities_logging.Reporter import Reporter


class Agent32(DefaultParty):
    """
    RAT4TA: Random Tit 4 Tat agent by group 32
    """
    def __init__(self, reporter: Reporter = None):
        super().__init__(reporter)
        self.getReporter().log(logging.INFO, "party is initialized")
        self._profile = None
        self._last_received_bid: Bid = None
        self.previousReceivedBids = []
        self.previousReceivedUtils = []
        self.hasGoodEnemy = True
        

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
            self._progress = self._settings.getProgress()

            # the profile contains the preferences of the agent over the domain
            self._profile = ProfileConnectionFactory.create(
                info.getProfile().getURI(), self.getReporter()
            )
        # ActionDone is an action send by an opponent (an offer or an accept)
        elif isinstance(info, ActionDone):
            action: Action = cast(ActionDone, info).getAction()

            # if it is an offer, set the last received bid
            if isinstance(action, Offer):
                self._last_received_bid = cast(Offer, action).getBid()
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
        return "RAT4TA: RAndom Tit-4-Tat Agent by group 32"
    
    # Detects wether an enemy is conceiding or hard lining.
    # This is done by analyzing the latest bits of the opponent.
    # It's not water tight but it functions good enough.
    def enemyConceiding(self):
        if len(self.previousReceivedUtils) < 10:
            return False
        value = np.std(self.previousReceivedUtils)
        last10Values = self.previousReceivedUtils[-10:]
        last5Better = (last10Values[0] + last10Values[1] + last10Values[2] + last10Values[3] + last10Values[4]) < (last10Values[-5] + last10Values[-1] + last10Values[-2] + last10Values[-3] + last10Values[-4])
        # print(value, np.std(last10Values))
        if value > 0.1: return True
        if np.std(last10Values) > 0.1 and last5Better: return True
        return False

    # execute a turn 
    def _myTurn(self):
        profile = self._profile.getProfile()
        # check if the last received offer if the opponent is good enough
        if self._isGood(self._last_received_bid):
            # if so, accept the offer
            action = Accept(self._me, self._last_received_bid)
        else:
            # if not, find a bid to propose as counter offer
            if self._last_received_bid is not None:
                self.previousReceivedBids.append([profile.getUtility(self._last_received_bid), self._last_received_bid])
                self.previousReceivedUtils.append(profile.getUtility(self._last_received_bid))
            bid = self._findBid()
            action = Offer(self._me, bid)
        # send the action
        return action

    # method that checks if we would agree with an offer
    def _isGood(self, bid: Bid) -> bool:
        if bid is None:
            return False
        profile = self._profile.getProfile()
        progress = self._progress.get(time.time() * 1000)
        
        #To still get some points from a hardlining enemy accept their last bid (since there is no gurantee they will accept our last bid)
        if progress >= 0.995:       return True
        # Checks if the enemy is also conceiding, otherwise only send bids of 0.95 utility
        if not self.hasGoodEnemy:   return profile.getUtility(bid) > 0.95
        # Send a bid as good as possible at the start
        if progress == 0:           return profile.getUtility(bid) > 0.98
        # Creates an linear conceiding line ending at 0.65 user utility at the end.
        return profile.getUtility(bid) > max (0.99 -  0.35 * progress, 0.65)
    
    # Used to sort the list of bids
    def takeUtility(elem, elem2):
        return elem2[0]
    
    def _findBid(self) -> Bid:
        # compose a list of all possible bids
        domain = self._profile.getProfile().getDomain()
        all_bids = AllBidsList(domain)
        profile = self._profile.getProfile()
        progress = self._progress.get(time.time() * 1000)
        self.validBidOptions = []
        self.allBidOptions = []


        self.previousReceivedBids.sort(key= self.takeUtility, reverse=True)
        
        # After 45% of the bids happend it will check if the enemy is conceiding.
        if progress > 0.45:
            self.hasGoodEnemy = True if self.enemyConceiding() else False
        # take 1000 attempts at finding a random bid that is acceptable to us
        for _ in range(1000):
            bid = all_bids.get(randint(0, all_bids.size() - 1))
            # Save all bid options generated in the format [[utility_1,bid_1], [utility_2,bid_2] , ... [utility_n,bid_n]]
            # This format is used to later sort on these values
            self.allBidOptions.append([profile.getUtility(bid), bid])
            if self._isGood(bid):
                # Save all valid options in the before mentioned format. note that the bids are not sorted!
                self.validBidOptions.append([profile.getUtility(bid), bid])
        try: 
            # Sort all bid options so that some checks on the best util can be performed
            self.allBidOptions.sort(key= self.takeUtility, reverse=True)   
        except:
            print("\n")
        
        nextBid = None
        # Sends the best bid it received back to the other agent if it is the last bid
        if(progress >= 0.99 and len(self.previousReceivedBids) > 0):
            nextBid = self.previousReceivedBids[0]
        # checks if a previous received bit is better than the current selected option. If so send back that bid
        elif(len(self.previousReceivedBids) > 0 and len(self.validBidOptions) > 0 and self.previousReceivedBids[0][0] > self.validBidOptions[0][0]):
            nextBid = self.previousReceivedBids[0]
        else:
        # Send back a random valid bid if there is one, otherwise send the best bid for our selves. 
        # (the first bid in the validBidOptions list is already random since it isnt sorted)
            nextBid = self.validBidOptions[0] if len(self.validBidOptions) > 0  else self.allBidOptions[0]
        # return the bid
        return nextBid[1]