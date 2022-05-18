from abc import ABC, abstractmethod
from geniusweb.issuevalue.Domain import Domain
from geniusweb.issuevalue.Bid import Bid
from geniusweb.references.Parameters import Parameters
from geniusweb.actions.Action import Action
from geniusweb.progress.Progress import Progress


class OpponentModel(ABC):
    '''
    An opponentmodel estimates a {@link UtilitySpace} from received opponent
    actions.
    <h2>Requirement</h2> A OpponentModel must have a constructor that takes the
    Domain as argument. unfortunately this can not be enforced in a java
    interface

    <p>
    <em>MUST</em> have an empty constructor as these are also used as part of the
    BOA framework.
    '''

    @abstractmethod
    def With(self, domain: Domain, resBid: Bid) -> "OpponentModel":
        '''
        Initializes the model. This function must be called first after
        constructing an instance. It can also be called again later, if there is
        a change in the domain or resBid.
        <p>
        This late-initialization is to support boa models that have late
        initialization.

        @param domain the domain to work with. Must be not null.
        @param resBid the reservation bid, or null if no reservationbid is
                      available.
        @return OpponentModel that uses given domain and reservationbid.
        '''

    @abstractmethod
    def WithParameters(self, parameters: Parameters) -> "OpponentModel":
        '''
        @param parameters Opponent-model specific {@link Parameters}
        @return an updated OpponentMode, with parameters used. Each
                implementation of OpponentModel is free to use parameters as it
                likes. For instance to set learning speed.
        '''

    @abstractmethod
    def WithAction(self, action: Action, progress: Progress) -> "OpponentModel":
        '''
        Update this with a new action that was done by the opponent that this
        model is modeling. {@link #with(Domain, Bid)} must be called before
        calling this.

        @param action   the new incoming action.
        @param progress the current progress of the negotiation. Calls to this
                        must be done with increasing progress.
        @return the updated {@link OpponentModel}
        '''
