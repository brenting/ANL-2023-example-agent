import logging
import numpy as np
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
from geniusweb.profile.utilityspace.LinearAdditiveUtilitySpace import LinearAdditiveUtilitySpace
from geniusweb.profileconnection.ProfileConnectionFactory import ProfileConnectionFactory
from geniusweb.progress.ProgressTime import ProgressTime
from geniusweb.references.Parameters import Parameters
from tudelft_utilities_logging.ReportToLogger import ReportToLogger

class agentBidHistory:
    def __init__(self):
        self.bidHistory = []

    def addBid(self, bid, label):
        self.bidHistory.append((bid, label))

class Agent007(DefaultParty):
    """Agent007"""
    def __init__(self):
        super().__init__()
        self._profileint: LinearAdditiveUtilitySpace = None
        self.lastOfferedBid = None
        self.logger: ReportToLogger = self.getReporter()
        self.logger.log(logging.INFO, "party is initialized")
        self.me: PartyId = None
        self.progress: ProgressTime = None
        self.settings: Settings = None
        self.domain: Domain = None
        self.parameters: Parameters = None
        self.other: str = None
        self.storage_dir: str = None
        self.bidHistory = None

    def notifyChange(self, data: Inform):
        """ Arg: info (Inform): Contains either a request for action or information.  """
        if isinstance(data, Settings):
            self.settings = cast(Settings, data)
            self.me = self.settings.getID()
            self.progress = self.settings.getProgress()
            self._profileint = ProfileConnectionFactory.create(   # the profile contains the preferences of the agent over the domain
                data.getProfile().getURI(), self.getReporter()
            )
            self.parameters = self.settings.getParameters()
            self.storage_dir = self.parameters.get("storage_dir")
            self.domain = self._profileint.getProfile().getDomain()
            self._profileint.close()
            self.rejected_bids = []
            self.bidHistory = agentBidHistory()
            self.issues = [issue for issue in sorted(self.domain.getIssues())]
            self.num_values_in_issue = [self.domain.getValues(issue).size() for issue in self.issues]
            self.bid_dict = self.bid_decode()

        elif isinstance(data, ActionDone):  # if opponent answered (reject or accept)            
            action: Action = data.getAction()
            if isinstance(action, Offer):   # [1] if opponent respond by reject our offer + proposed his offer
                if self.lastOfferedBid: # if we have already proposed an offer before
                    self.rejected_bids.append(self.lastOfferedBid)
                    self.bidHistory.addBid(self.bid_encode(self.lastOfferedBid), 0)  # opponent rejected our offer (negative label)
                actor = action.getActor()
                self.other = str(actor).rsplit("_", 1)[0]   # obtain the name of the opponent, cutting of the position ID.
                self.lastOfferedBid = cast(Offer, action).getBid()
                self.bidHistory.addBid(self.bid_encode(self.lastOfferedBid), 1)  # opponent offer (positive label)
            else:   # if [2] opponent accepted our offer
                self.bidHistory.addBid(self.bid_encode(self.lastOfferedBid), 1)  # opponent accepted our offer (positive label)
        elif isinstance(data, YourTurn):    # [3] YourTurn notifies you that it is your turn to act
            action = self.chooseAction()
            self.send_action(action)
        elif isinstance(data, Finished):    # [2] Finished will be send if the negotiation has ended (through agreement or deadline)
            self.save_data()
            self.logger.log(logging.INFO, "party is terminating:")
            super().terminate() # terminate the agent MUST BE CALLED
        else:
            self.logger.log(logging.WARNING, "Ignoring unknown info " + str(data))

    def send_action(self, action: Action):
        """Sends an action to the opponent(s) """
        self.getConnection().send(action)

    def getCapabilities(self) -> Capabilities:
        return Capabilities(set(["SAOP"]),set(["geniusweb.profile.utilityspace.LinearAdditive"]))

    def getDescription(self) -> str:
        return "Agent007 for the ANL 2022 competition"

    def save_data(self):
        """This method is called after the negotiation is finished. It can be used to store data
        for learning capabilities. Note that no extensive calculations can be done within this method.
        Taking too much time might result in your agent being killed, so use it for storage only.
        """
        data = "Data for learning (see README.md)"
        with open(f"{self.storage_dir}/data.md", "w") as f:
            f.write(data)

    def bid_decode(self):
        ''' perform decoding on the bid'''
        bid_dict = {}
        for bid in AllBidsList(self.domain):
            bid_vals = tuple(self.domain.getValues(issue).getValues().index(bid.getValue(issue)) for issue in self.issues)
            bid_dict[bid_vals] = bid
        return bid_dict

    def bid_encode(self, bid: Bid):
        ''' perform One Hot Encoding on the bid'''
        bid_vals = [self.domain.getValues(issue).getValues().index(bid.getValue(issue)) for issue in self.issues]
        total_num_values = sum(self.num_values_in_issue)
        ohe_vec = np.zeros(1+total_num_values)  # added 1 for bias
        ohe_vec[0] = 1.0    # the bias term
        start = 1
        for i in range(len(self.num_values_in_issue)):
            ohe_vec[start + bid_vals[i]] = 1.0
            start += self.num_values_in_issue[i]
        return ohe_vec

    def chooseAction(self):
        ''' Choose if to accept the last offer or make a new offer
        @return The chosen action
        '''
        progress = self.progress.get(time() * 1000)
        if self.shouldAccept():
            action = Accept(self.me, self.lastOfferedBid) 
        elif progress > 0.7:    # if we have enough data
            nextBid = self.get_bid()
            self.lastOfferedBid = nextBid
            action = Offer(self.me, nextBid)
        else:
            nextBid = self.findNextBid()
            self.lastOfferedBid = nextBid
            action = Offer(self.me, nextBid)
        return action

    def shouldAccept(self):
        '''
        @return Whether to accept the last bid or offer the nextBid
        '''
        progress = self.progress.get(time() * 1000)
        if self.lastOfferedBid == None:
            return False
        if progress > 0.97:
            return True
        if progress > 0.9 and self._profileint.getProfile().getUtility(self.lastOfferedBid) > 0.5:
            return True
        if progress > 0.8 and self._profileint.getProfile().getUtility(self.lastOfferedBid) > 0.6:
            return True
        return False

    def get_bid(self):
        issue_pos = [1]+[sum(self.num_values_in_issue[:i])+1 for i in range(1, len(self.num_values_in_issue))]
        profile = self._profileint.getProfile()
        issue_weight = [float(profile.getWeights()[issue]) for issue in profile.getWeights()]
        utilities = [profile.getUtilities()[issue] for issue in profile.getUtilities()]
        issues_values = [[float(v) for v in util.getUtilities().values()] for util in utilities]
        
        total_num_values = sum(self.num_values_in_issue)
        offered = np.zeros(1+total_num_values)  # added 1 for bias
        for bid in self.bidHistory.bidHistory:
            if bid[1] == 1:
                offered = np.add(offered, bid[0])

        issues_offered = [offered[v_pos: v_pos+v_len] for (v_pos, v_len) in zip(issue_pos, self.num_values_in_issue)]
        vec = []
        for i in range(len(self.issues)):
            avg = sum(issue_weight) / len(issue_weight)
            weight_ = issue_weight[i]/avg
            avg = sum(issues_offered[i]) / len(issues_offered[i])
            issues_offered_ =  [issue_offered/avg for issue_offered in issues_offered[i]]
            avg = (sum(issues_values[i])/len(issues_values[i]))
            issues_values_ = [issue_value/avg for issue_value in issues_values[i]]
            candidates = [(j,offer,val) for (j,offer,val) in zip(range(len(issues_offered_)), issues_offered_, issues_values_) if (offer >= 1 and val >= 1)]
            if len(candidates) == 0:
                if weight_ >= 1:
                    value_id = np.argmax(issues_values_)    # select best for my agent
                else:
                    value_id = np.argmax(issues_offered_)   # select best for opponent
            elif len(candidates) == 1:
                value_id = candidates[0][0]  # select best for both my agent and opponent
            else:
                values_ids, offers, values = zip(*candidates)
                if weight_ >= 1:
                    id = np.argmax(values)  # select best for my agent
                else:
                    id = np.argmax(offers)  # select best for opponent
                value_id = values_ids[id]
            vec.append(value_id)
        bid = self.bid_dict[tuple(vec)]
        return bid

    def findNextBid(self):
        '''
        @return The next bid to offer
        '''
        all_bids = AllBidsList(self.domain)
        bestBidEvaluation = 0
        nextBid = None
        for _ in range(500):
            domain_size = all_bids.size()
            id = np.random.randint(domain_size)
            bid = all_bids.get(id)
            bid_utility = float(self._profileint.getProfile().getUtility(bid))
            if bid_utility >= bestBidEvaluation:
                nextBid = bid
                bestBidEvaluation = bid_utility
        return nextBid
