import logging
from random import randint
from time import time
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
from geniusweb.profile.utilityspace.LinearAdditiveUtilitySpace import (
    LinearAdditiveUtilitySpace,
)
from geniusweb.profileconnection.ProfileConnectionFactory import (
    ProfileConnectionFactory,
)
from geniusweb.progress.ProgressTime import ProgressTime
from geniusweb.references.Parameters import Parameters
from tudelft_utilities_logging.ReportToLogger import ReportToLogger

#from agents.template_agent.utils.opponent_model import OpponentModel


class MiCROAgent(DefaultParty):
    """
    Implementation of the MiCRO strategy for ANAC 2022. MiCRO is a very simple strategy that just proposes all possible bids of the domain one by one, in order of decreasing utility, as long as the opponent keeps making new proposals as well.
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
#        self.opponent_model: OpponentModel = None
        self.logger.log(logging.INFO, "party is initialized")
        
        self.allMyBidsSorted: list = None
        self.receivedBids = set()
        self.numUniqueProposalsMadeByMe = 0
        self.reservationValue = 0 # in ANAC 2022 the reservation value is always 0, so actually we don't really need this value.
        
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
            
         
            #Create a sorted list containing all possible bids.
            domain = self.profile.getDomain()
            all_bids = AllBidsList(domain)
            self.allMyBidsSorted = list(all_bids)
            self.allMyBidsSorted.sort(reverse=True,key=self.profile.getUtility) 
            
            #Test that it is sorted correctly.
            #for bid in self.allMyBidsSorted:
            #   print(bid, self.profile.getUtility(bid))

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
        return "Implementation of the MiCRO strategy for ANAC 2022. MiCRO is a very simple strategy that just proposes all possible bids of the domain one by one, in order of decreasing utility, as long as the opponent keeps making new proposals as well."

    def opponent_action(self, action):
        """Process an action that was received from the opponent.

        Args:
            action (Action): action of opponent
        """
        # if it is an offer, set the last received bid
        if isinstance(action, Offer):

            bid = cast(Offer, action).getBid()
            
            # set bid as last received
            self.last_received_bid = bid
            
            # add bid to set of all received bids.
            self.receivedBids.add(bid)
            
            #print("")
            #print("Newly received bid:")
            #print(bid)
            #print("Bids received so far:")
            #for earlierBid in self.receivedBids:
            #    print(earlierBid)

    def my_turn(self):
        """This method is called when it is our turn. It should decide upon an action
        to perform and send this action to the opponent.
        """
        
        #1. Determine whether or not we should concede (i.e make a new proposal as opposed to repeat an earlier proposal)
        readyToConcede = self.numUniqueProposalsMadeByMe <= len(self.receivedBids)

        #2. Determine whether to accept the opponent's last proposal or not.
        if self.last_received_bid != None:
                
            accept = self.acceptanceStrategy(readyToConcede)
            
            if accept:
                action = Accept(self.me, self.last_received_bid)
                self.send_action(action)
                return
               
               
        # 3. If we did not accept, then make a counter-proposal (either a new one, or repeat an old one). 
        
            # 3a. Get the next bid from our sorted list, after the last one that we have already proposed.
        myNextBid = self.allMyBidsSorted[self.numUniqueProposalsMadeByMe]
            
            # 3b. Determine whether to propose that one or to repeat one we already proposed before.
        if readyToConcede and self.profile.getUtility(myNextBid) > self.reservationValue:
                    
            # Propose the next bid in the list.
            
            self.numUniqueProposalsMadeByMe += 1
            
            action = Offer(self.me, myNextBid)
            self.send_action(action)
            return
            
        else:
            
            # Randomly pick a bid we have already proposed before.
            randomIndex = randint(0, self.numUniqueProposalsMadeByMe-1)
            randomBid = self.allMyBidsSorted[randomIndex]
            action = Offer(self.me, randomBid)
            self.send_action(action)
            return

    def acceptanceStrategy(self, readyToConcede: bool) -> bool:

        utilityOfLastReceivedOffer = self.profile.getUtility(self.last_received_bid)
        
        if utilityOfLastReceivedOffer <= self.reservationValue:
            return False;
        
        if readyToConcede:
            lowestAcceptableBid = self.allMyBidsSorted[self.numUniqueProposalsMadeByMe]  #The next bid we are willing to propose. 
        else:
            lowestAcceptableBid = self.allMyBidsSorted[self.numUniqueProposalsMadeByMe-1] # The lowest bid we have already proposed.
        
        lowestAcceptableUtility = self.profile.getUtility(lowestAcceptableBid);
        
        
        return utilityOfLastReceivedOffer >= lowestAcceptableUtility;



    def save_data(self):
        """This method is called after the negotiation is finished. It can be used to store data
        for learning capabilities. Note that no extensive calculations can be done within this method.
        Taking too much time might result in your agent being killed, so use it for storage only.
        """
        #data = "Data for learning (see README.md)"
        #with open(f"{self.storage_dir}/data.md", "w") as f:
        #    f.write(data)
        pass