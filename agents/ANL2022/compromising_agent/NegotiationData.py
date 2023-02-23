class NegotiationData:
    """The class hold the negotiation data that is obtain during a negotiation
    session.It will be saved to disk after the negotiation has finished.
    this negotiation used to update the learning data of the agent.
    """
    __tSplit = 40

    def __init__(self):
        self.__maxReceivedUtil: float = 0.0
        self.__agreementUtil: float = 0.0
        self.__opponentName: str = None
        self.__opponentUtil: float = 0.0
        self.__opponentMaxReject: list = [0.0] * self.__tSplit
        self.__opponentUtilByTime: list = [0.0] * self.__tSplit

    def encode(self, paramList: list):
        """ This function get deserialize json
        """
        self.__maxReceivedUtil = paramList[0]
        self.__agreementUtil = paramList[1]
        self.__opponentName = paramList[2]
        self.__opponentUtil = paramList[3]
        self.__opponentMaxReject = paramList[4]
        self.__opponentUtilByTime = paramList[5]

    def addAgreementUtil(self, agreementUtil: float):
        self.__agreementUtil = agreementUtil
        if (agreementUtil > self.__maxReceivedUtil):
            self.__maxReceivedUtil = agreementUtil

    def addBidUtil(self, bidUtil: float):
        if (bidUtil > self.__maxReceivedUtil):
            self.__maxReceivedUtil = bidUtil

    def addRejectUtil(self, index: int, bidUtil: float):
        if (bidUtil > self.__opponentMaxReject[index]):
            self.__opponentMaxReject[index] = bidUtil

    def updateOpponentOffers(self, opSum: list, opCounts: list):
        for i in range(self.__tSplit):
            self.__opponentUtilByTime[i] = opSum[i] / opCounts[i] if opCounts[i] > 0 else 0.0

    def setOpponentName(self, opponentName: str):
        self.__opponentName = opponentName

    def setOpponentUtil(self, oppUtil: float):
        self.__opponentUtil = oppUtil

    def getOpponentName(self):
        return self.__opponentName

    def getMaxReceivedUtil(self):
        return self.__maxReceivedUtil

    def getAgreementUtil(self):
        return self.__agreementUtil

    def getOpponentUtil(self):
        return self.__opponentUtil

    def getOpponentUtilByTime(self):
        return self.__opponentUtilByTime

    def getOpponentMaxReject(self):
        return self.__opponentMaxReject
