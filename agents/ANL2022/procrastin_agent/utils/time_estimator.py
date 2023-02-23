import numpy as np
from sklearn.linear_model import LinearRegression

"""
Key assumptions:
1. turns_left will only be called during our agent's "turn"
2. times will be added to their respective lists using the progress function
"""
class TimeEstimator:

    def __init__(self):
        self.self_times = []
        self.rounds = []
        #self.roundsquare = []
        # self.outliers = []
        self.opp_times = []
        self.self_diff = []
        self.FRAME_LENGTHS = [10000, 100]
        self.UPDATE_PERIODS = [1, 1]
        self.models = [None for _ in range(len(self.FRAME_LENGTHS))]
        self.stdevs = [None for _ in range(len(self.FRAME_LENGTHS))]
        self.self_times_adj = []
        self.opp_times_adj = []
        
        self.round_count = 0
        self.outlier_count = 0
        self.time_factor = 1.0

    def update_time_factor(self, time_factor: float):
        self.time_factor = time_factor

    def get_new_time_factor(self, predicted_negs_left: list, bid_pool_size: int):
        if len(predicted_negs_left) > bid_pool_size:
            return self.time_factor / max((predicted_negs_left[-bid_pool_size] / bid_pool_size), 0.01)
        elif len(predicted_negs_left) > 10:
            return self.time_factor / max((predicted_negs_left[5] / (len(predicted_negs_left) - 5)), 0.01)
        elif len(predicted_negs_left):
            return self.time_factor / max(predicted_negs_left[-1], 0.01)
        else:
            return self.time_factor

    def self_times_add(self, time: float):
        self.round_count += 1
        self.self_times.append(time)
        self.rounds.append(self.round_count)
        if self.round_count > 5 and time > np.mean(self.self_times) + 3 * np.std(self.self_times):
            self.outlier_count += 1
        # self.outliers.append(self.outlier_count)
        #self.roundsquare.append(self.round_count * self.round_count)

        self.update_model()
    
    def opp_times_add(self, value: float):
        self.opp_times.append(value)
        self.self_diff.append(value - self.self_times[-1])

    def _generate_model(self, frame_length):
        y_list = self.self_times if len(self.self_times) < frame_length else self.self_times[-frame_length:]
        x1_list = self.rounds if len(self.rounds) < frame_length else self.rounds[-frame_length:]
        # x2_list = self.roundsquare if len(self.roundsquare) < frame_length else self.rounds[-frame_length:]
        y = np.array(y_list)
        x1 = np.array(x1_list)
        # x2 = np.array(x2_list)
        # X = np.stack([x1, x2]).transpose((1,0))
        X = np.array([x1]).transpose((1,0))
        model1 = LinearRegression().fit(X, y)
        # model2 = LinearRegression().fit(X2, y)
        y_pred = model1.predict(X)
        res = y_pred - y
        stdev = np.std(res)
        return model1, stdev

    def update_model(self):
        issue_count = len(self.self_times)
        for i, (frame_length, update_period) in enumerate(zip(self.FRAME_LENGTHS, self.UPDATE_PERIODS)):
            if issue_count % update_period == 0 or i < 5:
                model, stdev = self._generate_model(frame_length)
                self.models[i] = model
                self.stdevs[i] = stdev

    def turns_left(self, time):
        """
        If your turn starts at time, how many turns are left?
        """
        if len(self.self_times) <= 1:
            return 2000
        p_list = [np.append(model.coef_, model.intercept_ - 1.0) for model in self.models]
        # final_turn_counts = np.array([np.max(np.roots(p)) / (1.0 + stdev) for p, stdev in zip(p_list, self.stdevs)])
        final_turn_counts = np.array([np.max(np.roots(p)) / (1.0 + stdev) * self.time_factor for p, stdev in zip(p_list, self.stdevs)])

        p_list = [np.append(model.coef_, model.intercept_ - time) for model in self.models]
        # time_turn_counts = np.array([np.max(np.roots(p)) / (1.0 + stdev) for p, stdev in zip(p_list, self.stdevs)])
        time_turn_counts = np.array([np.max(np.roots(p)) / (1.0 + stdev) * self.time_factor for p, stdev in zip(p_list, self.stdevs)])
        
        return int(np.min(final_turn_counts - time_turn_counts))

    # #adds adjusted values to the adjusted lists by subtracting the "start point" provided by the preceding progress value from each value
    # def lists_adjust(self):
    #     #first iteration
    #     if self.idx == 0:
    #         #our agent made the first bid
    #         if self.self_times[0] < self.opp_times[0]:
    #             self.self_times_adj.append(self.self_times[0])
    #             self.opp_times_adj.append(self.opp_times[self.idx] - self.self_times[self.idx])
    #             self.idx += 1
    #             while self.idx < len(self.self_times):
    #                 self.self_times_adj.append(self.self_times[self.idx]-self.opp_times[self.idx-1])
    #                 self.opp_times_adj.append(self.opp_times[self.idx]-self.self_times[self.idx])
    #                 self.idx += 1
    #         #the opponent made the first bid
    #         else:
    #             self.self_times_adj.append(self.self_times[self.idx]-self.opp_times[self.idx])
    #             self.opp_times_adj.append(self.opp_times[0])
    #             self.opp_times_adj.append(self.opp_times[self.idx+1]-self.self_times[self.idx])
    #             self.idx += 1
    #             while self.idx < len(self.self_times):
    #                 self.self_times_adj.append(self.self_times[self.idx]-self.opp_times[self.idx])
    #                 self.opp_times_adj.append(self.opp_times[self.idx+1]-self.self_times[self.idx])
    #                 self.idx += 1
    #     #further iterations
    #     else: 
    #         #continuing case where our agent made the first bid
    #         if self.self_times[self.idx] < self.opp_times[self.idx]:
    #             while self.idx < len(self.self_times):
    #                 self.self_times_adj.append(self.self_times[self.idx]-self.opp_times[self.idx-1])
    #                 self.opp_times_adj.append(self.opp_times[self.idx]-self.self_times[self.idx])
    #                 self.idx += 1
    #         #cintinuing case where opponent made the first bid
    #         else:
    #             while self.idx < len(self.self_times):
    #                 self.self_times_adj.append(self.self_times[self.idx]-self.opp_times[self.idx])
    #                 self.opp_times_adj.append(self.opp_times[self.idx+1]-self.self_times[self.idx])
    #                 self.idx += 1

    # #feeder function to be deleted after regression implemented
    # def opp_avg(self):
    #     Sum = sum(self.opp_times_adj)
    #     O_avg = Sum / len(self.opp_times_adj)
    #     return O_avg
    
    # #feeder function to be deleted after regression implemented
    # def self_avg(self):
    #     Sum = sum(self.self_times_adj)
    #     S_avg = Sum/len(self.self_times_adj)
    #     return S_avg
    
    # def turns_left(self, progress: float):
    #     self.lists_adjust()
    #     opp_time = self.opp_avg()
    #     self_time = self.self_avg()
    #     i = 0
    #     count = 0

    #     #make sure order is correct
    #     while progress < 1:
    #         if (i % 2 == 0):
    #             progress += self_time
    #         else:
    #             progress += opp_time
            
    #         count += 1
    #         i += 1

    #     return count