import json
import logging
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

from .utils.Pinar_Agent_Brain import Pinar_Agent_Brain


class Pinar_Agent(DefaultParty):
    def __init__(self):
        super().__init__()
        self.logger: ReportToLogger = self.getReporter()

        self.domain: Domain = None
        self.parameters: Parameters = None
        self.profile: LinearAdditiveUtilitySpace = None
        self.sorted_bids = None

        self.progress: ProgressTime = None
        self.me: PartyId = None
        self.opponent_id: str = None
        self.settings: Settings = None
        self.storage_dir: str = None

        self.last_received_bid: Bid = None

        self.agent_brain = Pinar_Agent_Brain()

        self.storage_data = {}
        self.isFirstRound = True
        self.last_trained_time = 0

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
            all_bids = AllBidsList(self.domain)
            if not self.sorted_bids:
                self.sorted_bids = sorted(all_bids, key=lambda x: self.profile.getUtility(x),
                                          reverse=True)
            self.agent_brain.fill_domain_and_profile(self.domain, self.profile)

            profile_connection.close()

        # ActionDone informs you of an action (an offer or an accept)
        # that is performed by one of the agents (including yourself).
        elif isinstance(data, ActionDone):
            action = cast(ActionDone, data).getAction()
            actor = action.getActor()

            # ignore action if it is our action
            if actor != self.me:
                # obtain the name of the opponent, cutting of the position ID.
                self.opponent_id = str(actor).rsplit("_", 1)[0]

                if self.isFirstRound:
                    self.load_data()
                    self.isFirstRound = False
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
        return "Precious Intelligent Negotiation Agreement Robot(Pinar) that empowered by LightGBM tries to find opponent weak side"

    def opponent_action(self, action):
        """Process an action that was received from the opponent.

        Args:
            action (Action): action of opponent
        """
        # if it is an offer, set the last received bid
        if isinstance(action, Offer):
            bid = cast(Offer, action).getBid()
            progress_time = float(self.progress.get(time() * 1000))
            if bid not in self.agent_brain.offers_unique:
                if len(self.agent_brain.offers_unique) <= 8 and progress_time < 0.81:
                    self.agent_brain.add_opponent_offer_to_self_x_and_self_y(bid, progress_time)
                    self.agent_brain.evaluate_data_according_to_lig_gbm(progress_time)
                    self.last_trained_time = progress_time
                elif self.last_trained_time + 0.1 > progress_time and self.agent_brain.lgb_model is not None:
                    self.agent_brain.evaluate_opponent_utility_for_all_my_important_bid(progress_time)
                    self.last_trained_time = progress_time

            self.agent_brain.keep_opponent_offer_in_a_list(bid, progress_time)
            # set bid as last received
            self.last_received_bid = bid

    def my_turn(self):
        """This method is called when it is our turn. It should decide upon an action
        to perform and send this action to the opponent.
        """
        # check if the last received offer is good enough
        if self.accept_condition(self.last_received_bid):
            # if so, accept the offer
            action = Accept(self.me, self.last_received_bid)
        else:
            # if not, find a bid to propose as counter offer
            progress_time = float(self.progress.get(time() * 1000))
            bid = self.agent_brain.find_bid(progress_time)
            action = Offer(self.me, bid)

        # send the action
        self.send_action(action)

    def save_data(self):
        """This method is called after the negotiation is finished. It can be used to store data
        for learning capabilities. Note that no extensive calculations can be done within this method.
        Taking too much time might result in your agent being killed, so use it for storage only.
        """
        try:
            if 'offerNumberUnique' in self.storage_data.keys():
                self.storage_data['offerNumberUnique'].append(len(self.agent_brain.offers_unique))
            else:
                self.storage_data['offerNumberUnique'] = [len(self.agent_brain.offers_unique)]
            if 'acceptance_condition' in self.storage_data.keys():
                self.storage_data['acceptance_condition'].append(self.agent_brain.acceptance_condition)
            else:
                self.storage_data['acceptance_condition'] = [self.agent_brain.acceptance_condition]
            if 'model_feature_importance' in self.storage_data.keys():
                self.storage_data['model_feature_importance'].append(self.agent_brain.model_feature_importance())
            else:
                self.storage_data['model_feature_importance'] = [self.agent_brain.model_feature_importance()]

            with open(f"{self.storage_dir}/{self.opponent_id}data.md", "w") as f:
                f.write(json.dumps(self.storage_data))

        except Exception:
            pass

    def load_data(self):
        if self.opponent_id is not None and self.storage_dir is not None:
            try:
                with open(self.storage_dir + "/" + self.opponent_id + "data.md") as file:
                    self.storage_data = json.load(file)
                    self.this_session_is_first_match_for_this_opponent = False
            except Exception:
                pass

    def accept_condition(self, bid: Bid) -> bool:
        if bid is None:
            return False

        # progress of the negotiation session between 0 and 1 (1 is deadline)
        progress = self.progress.get(time() * 1000)

        return self.agent_brain.is_acceptable(bid, progress)
