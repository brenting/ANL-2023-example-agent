import math
from math import sqrt

from .NegotiationData import NegotiationData


class LearnedData:
    """This class hold the learned data of our agent.
    """

    __tSplit: int = 40
    __tPhase: float = 0.2
    __newWeight: float = 0.3
    __newWeightForReject: float = 0.3
    __smoothWidth: int = 3  # from each side of the element
    __smoothWidthForReject: int = 3  # from each side of the element
    __opponentDecrease: float = 0.65
    __defualtAlpha: float = 10.7

    def __init__(self):

        self.__opponentName: str = None
        # average utility of agreement
        self.__avgUtility: float = 0.0
        # num of negotiations against this opponent
        self.__numEncounters: int = 0
        self.__avgMaxUtilityOpponent: float = 0.0

        # our new data structures
        self.__stdUtility: float = 0.0
        self.__negoResults: list = []
        self.__avgOpponentUtility: float = 0.0
        self.__opponentAlpha: float = 0.0
        self.__opponentUtilByTime: list = []
        self.__opponentMaxReject: list = [0.0] * self.__tSplit

    def encode(self, paramList: list):
        """ This function get deserialize json
        """
        self.__opponentName = paramList[0]
        self.__avgUtility = paramList[1]
        self.__numEncounters = paramList[2]
        self.__avgMaxUtilityOpponent = paramList[3]
        self.__stdUtility = paramList[4]
        self.__negoResults = paramList[5]
        self.__avgOpponentUtility = paramList[6]
        self.__opponentAlpha = paramList[7]
        self.__opponentUtilByTime = paramList[8]
        self.__opponentMaxReject = paramList[9]

    def update(self, negotiationData: NegotiationData):
        """ Update the learned data with a negotiation data of a previous negotiation
               session
               negotiationData NegotiationData class holding the negotiation data
               that is obtain during a negotiation session.
           """
        # Keep track of the average utility that we obtained Double
        newUtil = negotiationData.getAgreementUtil() if (negotiationData.getAgreementUtil() > 0) \
            else self.__avgUtility - 1.1 * pow(self.__stdUtility, 2)

        self.__avgUtility = (self.__avgUtility * self.__numEncounters + newUtil) \
                            / (self.__numEncounters + 1)

        # add utility to UtiList calculate std deviation of results
        self.__negoResults.append(negotiationData.getAgreementUtil())
        self.__stdUtility = 0.0

        for util in self.__negoResults:
            self.__stdUtility += pow(util - self.__avgUtility, 2)
        self.__stdUtility = sqrt(self.__stdUtility / (self.__numEncounters + 1))

        # Track the average value of the maximum that an opponent has offered us across
        # multiple negotiation sessions Double
        self.__avgMaxUtilityOpponent = (
                                                   self.__avgMaxUtilityOpponent * self.__numEncounters + negotiationData.getMaxReceivedUtil()) \
                                       / (self.__numEncounters + 1)

        self.__avgOpponentUtility = (
                                                self.__avgOpponentUtility * self.__numEncounters + negotiationData.getOpponentUtil()) \
                                    / (self.__numEncounters + 1)

        # update opponent utility over time
        opponentTimeUtil: list = [0.0] * self.__tSplit if self.__opponentUtilByTime == [] else self.__opponentUtilByTime
        # update opponent reject over time
        opponentMaxReject: list = [0.0] * self.__tSplit if self.__opponentMaxReject == [] else self.__opponentMaxReject

        # update values in the array
        newUtilData: list = negotiationData.getOpponentUtilByTime()
        newOpponentMaxReject = negotiationData.getOpponentMaxReject()

        if self.__numEncounters == 0:
            self.__opponentUtilByTime = newUtilData
            self.__opponentMaxReject = newOpponentMaxReject

        else:
            # find the ratio of decrease in the array, for updating 0 - s in the array
            ratio: float = ((1 - self.__newWeight) * opponentTimeUtil[0] + self.__newWeight * newUtilData[0]) / \
                           opponentTimeUtil[0] \
                if opponentTimeUtil[0] > 0.0 else 1

            # update the array
            for i in range(self.__tSplit):
                if (newUtilData[i] > 0):
                    opponentTimeUtil[i] = (
                                (1 - self.__newWeight) * opponentTimeUtil[i] + self.__newWeight * newUtilData[i])
                else:
                    opponentTimeUtil[i] *= ratio

            self.__opponentUtilByTime = opponentTimeUtil

            # find the ratio of decrease in the array, for updating 0 - s in the array
            ratio: float = ((1 - self.__newWeightForReject) * opponentMaxReject[0] + self.__newWeightForReject *
                            newOpponentMaxReject[0]) / \
                           opponentMaxReject[0] \
                if opponentMaxReject[0] > 0.0 else 1

            # update the array
            for i in range(self.__tSplit):
                if (newOpponentMaxReject[i] > 0):
                    opponentMaxReject[i] = (
                            (1 - self.__newWeightForReject) * opponentMaxReject[i] + self.__newWeightForReject *
                            newOpponentMaxReject[i])
                else:
                    opponentMaxReject[i] *= ratio

            self.__opponentMaxReject = opponentMaxReject

        self.__opponentAlpha = self.calcAlpha()

        # Keep track of the number of negotiations that we performed
        self.__numEncounters += 1

    def calcAlpha(self):
        # smoothing with smooth width of smoothWidth
        alphaArray: list = self.getSmoothThresholdOverTime()

        # find the last index with data in alphaArray

        maxIndex: int = 0
        while maxIndex < self.__tSplit and alphaArray[maxIndex] > 0.2:
            maxIndex += 1

        # find t, time that threshold decrease by 50 %
        maxValue: float = alphaArray[0]
        minValue: float = alphaArray[max(maxIndex - self.__smoothWidth - 1, 0)]

        # if there is no clear trend-line, return default value
        if maxValue - minValue < 0.1:
            return self.__defualtAlpha

        t: int = 0
        while t < maxIndex and alphaArray[t] > (maxValue - self.__opponentDecrease * (maxValue - minValue)):
            t += 1

        calibratedPolynom: list = [572.83, -1186.7, 899.29, -284.68, 32.911]
        alpha: float = calibratedPolynom[0]

        tTime: float = self.__tPhase + (1 - self.__tPhase) * (
                    maxIndex * (float(t) / self.__tSplit) + (self.__tSplit - maxIndex) * 0.85) / self.__tSplit
        for i in range(1, len(calibratedPolynom)):
            alpha = alpha * tTime + calibratedPolynom[i]

        return alpha

    def getSmoothThresholdOverTime(self):
        # smoothing with smooth width of smoothWidth
        smoothedTimeUtil: list = [0.0] * self.__tSplit

        # ignore zeros in end of the array
        tSplitWithoutZero = self.__tSplit - 1
        while self.__opponentUtilByTime[tSplitWithoutZero] == 0 and tSplitWithoutZero > 0:
            tSplitWithoutZero -= 1
        tSplitWithoutZero += 1
        for i in range(tSplitWithoutZero):
            for j in range(max(i - self.__smoothWidth, 0), min(i + self.__smoothWidth + 1, tSplitWithoutZero)):
                smoothedTimeUtil[i] += self.__opponentUtilByTime[j]
            smoothedTimeUtil[i] /= (min(i + self.__smoothWidth + 1, tSplitWithoutZero) - max(i - self.__smoothWidth, 0))

        return smoothedTimeUtil

    def getSmoothRejectOverTime(self):
        # smoothing with smooth width of smoothWidth
        smoothedRejectUtil: list = [0.0] * self.__tSplit

        # ignore zeros in end of the array
        tSplitWithoutZero = self.__tSplit - 1
        while self.__opponentMaxReject[tSplitWithoutZero] == 0 and tSplitWithoutZero > 0:
            tSplitWithoutZero -= 1
        tSplitWithoutZero += 1
        for i in range(tSplitWithoutZero):
            for j in range(max(i - self.__smoothWidthForReject, 0),
                           min(i + self.__smoothWidthForReject + 1, tSplitWithoutZero)):
                smoothedRejectUtil[i] += self.__opponentMaxReject[j]
            smoothedRejectUtil[i] /= (min(i + self.__smoothWidthForReject + 1, tSplitWithoutZero) - max(
                i - self.__smoothWidthForReject, 0))

        return smoothedRejectUtil

    def getAvgUtility(self):
        return self.__avgUtility

    def getStdUtility(self):
        return self.__stdUtility

    def getOpponentAlpha(self):
        return self.__opponentAlpha

    def getOpUtility(self):
        return self.__avgOpponentUtility

    def getAvgMaxUtility(self):
        return self.__avgMaxUtilityOpponent

    def getOpponentEncounters(self):
        return self.__numEncounters

    def setOpponentName(self, opponentName):
        self.__opponentName = opponentName
