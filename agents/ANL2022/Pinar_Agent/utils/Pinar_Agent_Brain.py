import json
import random
import pandas as pd
import lightgbm as lgb

from geniusweb.bidspace.AllBidsList import AllBidsList
from geniusweb.issuevalue.Bid import Bid


class Pinar_Agent_Brain:
    def __init__(self):

        self.acceptance_condition = 0
        self.my_offered_number_of_time_from_ai = 0
        self.sorted_bids_agent_that_greater_than_065_df = pd.DataFrame()
        self.sorted_bids_agent_that_greater_than_065 = []

        self.reservationBid_utility = float(0)
        self.eva_util_val_acc_to_lgb_m_with_max_bids_for_agent = []
        self.sorted_bids_agent_df = None
        self.reservationBid: Bid = None
        self.sorted_bids_agent = None
        self.sorted_bids_agent_that_greater_than_goal_of_utility = []
        self.all_bid_list = None

        self.param = None

        self.lgb_model = None

        self.X = pd.DataFrame()
        self.Y = pd.DataFrame()

        self.domain = None
        self.profile = None
        self.issue_name_list = None
        self.temEnumDict = None

        self.offers = []
        self.offers_unique = []
        self.offers_unique_sorted = None

        self.number_of_bid_greater_than95 = 0
        self.percentage_of_greater_than95 = 0

        self.number_of_bid_greater_than85 = 0
        self.percentage_of_greater_than85 = 0

        self.goal_of_utility = 0.80
        self.number_of_goal_of_utility = None

    @staticmethod
    def get_goal_of_negoation_utility(x):
        if 0 <= x <= 0.05:
            a = float(-57.57067183) * float(x) * float(x)
            b = float(x) * float(7.50261378)
            c = float(1.59499339)
            d = a + b + c
            return float(d / 2)
        elif x > 0.05:
            return float(0.94)
        return float(0.80)

    def keep_opponent_offer_in_a_list(self, bid: Bid, progress_time: float):
        # keep track of all bids received
        self.offers.append(bid)

        if bid not in self.offers_unique:
            self.offers_unique.append(bid)
            if progress_time >= 0.9:
                self.offers_unique_sorted = sorted(self.offers_unique, key=lambda x: self.profile.getUtility(x),
                                                   reverse=True)

    def add_opponent_offer_to_self_x_and_self_y(self, bid, progress_time):
        bid_value_array = self.get_bid_value_array_for_data_frame_usage(bid)
        df = pd.DataFrame(bid_value_array)
        df = self.enumerate(df)
        self.X = pd.concat([self.X, df])
        if progress_time < 0.81:
            val = (float(0.99) - (float(0.14) * (float(progress_time))))
            """Y tarafına öyle bir değişken atamalıyım ki adamın utilitisi olmalı (kendi utilitime göre olsa daha mantıklı olabilir gibi şimdilik)"""
            new = pd.DataFrame([val])
            self.Y = pd.concat([self.Y, new])

    def fill_domain_and_profile(self, domain, profile):
        self.domain = domain
        self.profile = profile
        self.reservationBid = self.profile.getReservationBid()
        if self.reservationBid is not None:
            self.reservationBid_utility = self.profile.getUtility(self.reservationBid)
        self.issue_name_list = self.domain.getIssues()
        self.X = pd.DataFrame()
        self.Y = pd.DataFrame()
        self.temEnumDict = self.enumerate_enum_dict()
        self.all_bid_list = AllBidsList(domain)

        self.sorted_bids_agent = sorted(self.all_bid_list,
                                        key=lambda x: self.profile.getUtility(x),
                                        reverse=True)
        self.calculate_percantage_and_number()
        self.add_agent_first_n_bid_to_machine_learning_with_low_utility(self.sorted_bids_agent)

    def calculate_percantage_and_number(self):
        numb_95 = 0
        numb_85 = 0
        for i in self.sorted_bids_agent:
            utility = float(self.profile.getUtility(i))
            if utility > float(0.95):
                numb_95 = numb_95 + 1
            if utility > float(0.85):
                numb_85 = numb_85 + 1
            else:
                break
        self.number_of_bid_greater_than95 = numb_95
        self.number_of_bid_greater_than85 = numb_85

        self.percentage_of_greater_than95 = float(self.number_of_bid_greater_than95) / float(
            len(self.sorted_bids_agent))
        self.percentage_of_greater_than85 = float(self.number_of_bid_greater_than85) / float(
            len(self.sorted_bids_agent))

        self.goal_of_utility = self.get_goal_of_negoation_utility(float(self.percentage_of_greater_than85)) + float(
            0.01)
        numb_goal_util = 0
        self.sorted_bids_agent_df = pd.DataFrame()
        self.sorted_bids_agent_that_greater_than_065_df = pd.DataFrame()
        for i in self.sorted_bids_agent:
            utility = float(self.profile.getUtility(i))
            if utility > float(self.goal_of_utility):
                numb_goal_util = numb_goal_util + 1
            if utility > (float(self.goal_of_utility) - float(0.1)):
                self.sorted_bids_agent_that_greater_than_goal_of_utility.append(i)
                df_temp = pd.DataFrame(self.get_bid_value_array_for_data_frame_usage(i))
                df_temp = self.enumerate(df_temp)
                self.sorted_bids_agent_df = pd.concat([self.sorted_bids_agent_df, df_temp])
            if utility > 0.65:
                self.sorted_bids_agent_that_greater_than_065.append(i)
                df_temp = pd.DataFrame(self.get_bid_value_array_for_data_frame_usage(i))
                df_temp = self.enumerate(df_temp)
                self.sorted_bids_agent_that_greater_than_065_df = pd.concat(
                    [self.sorted_bids_agent_that_greater_than_065_df, df_temp])
            else:
                break
        self.number_of_goal_of_utility = numb_goal_util

    def evaluate_opponent_utility_for_all_my_important_bid(self, progress_time):
        self.eva_util_val_acc_to_lgb_m_with_max_bids_for_agent = []
        self.my_offered_number_of_time_from_ai = 0
        util_of_opponent = self.lgb_model.predict(self.sorted_bids_agent_that_greater_than_065_df)

        for index, i in enumerate(self.sorted_bids_agent_that_greater_than_065):
            util = float(self.profile.getUtility(i))
            if float(self.reservationBid_utility) <= util \
                    and (((float(0.93) - (
                    (float(0.95) - (self.goal_of_utility - float(0.18))) * float(progress_time))) < util)
                         and float(0.40) < util_of_opponent[index] < util - float(0.10)):
                self.eva_util_val_acc_to_lgb_m_with_max_bids_for_agent.append(i)

    def evaluate_data_according_to_lig_gbm(self, progress_time):
        length = len(self.offers_unique)
        if length >= 1 and (length % 2) == 0:
            self.train_machine_learning_model()
            self.evaluate_opponent_utility_for_all_my_important_bid(progress_time)

    def train_machine_learning_model(self):
        issue_list = []
        for issue in self.domain.getIssues():
            issue_list.append(issue)
        for col in issue_list:
            self.X[col] = self.X[col].astype('int')
        self.Y = self.Y.astype('float')
        train_data = lgb.Dataset(self.X, label=self.Y, feature_name=issue_list)
        if self.param is None:
            self.param = {
                'objective': 'cross_entropy',
                'learning_rate': 0.01,
                'force_row_wise': True,
                'feature_fraction': 1,
                'max_depth': 3,
                'num_leaves': 4,
                'boosting': 'gbdt',
                'min_data': 1,
                'verbose': -1
            }
        self.lgb_model = lgb.train(self.param, train_data)

    def call_model_lgb(self, bid):
        if self.lgb_model:
            prediction = self.lgb_model.predict(self._bid_for_model_prediction_to_df(bid))
            return float(prediction[0])
        else:
            return float(1)

    def get_bid_value_array_for_data_frame_usage(self, bid):
        bid_value_array = {}
        for issue in self.issue_name_list:
            bid_value_array[issue] = [bid.getValue(issue)]
        return bid_value_array

    def _bid_for_model_prediction_to_df(self, bid):
        df_temp = pd.DataFrame(self.get_bid_value_array_for_data_frame_usage(bid))
        df_temp = self.enumerate(df_temp)
        return df_temp

    def enumerate_enum_dict(self):
        issue_enums_dict = {}
        for issue in self.domain.getIssues():
            temp_enums = dict((y, x) for x, y in enumerate(set(self.domain.getIssuesValues()[issue])))
            issue_enums_dict[issue] = temp_enums
        return issue_enums_dict

    def enumerate(self, df):
        for issue in self.domain.getIssues():
            df[issue] = df[issue].map(self.temEnumDict[issue])
        return df

    def model_feature_importance(self):
        if self.lgb_model is not None:
            df = pd.DataFrame({'Value': self.lgb_model.feature_importance(), 'Feature': self.X.columns})
            result = df.to_json(orient="split")
            parsed = json.loads(result)
            return parsed
        return ""

    def util_add_agent_first_n_bid_to_machine_learning_with_low_utility(self, bid, ratio):
        bid_value_array = self.get_bid_value_array_for_data_frame_usage(bid)
        df = pd.DataFrame(bid_value_array)
        df = self.enumerate(df)
        self.X = pd.concat([self.X, df])
        util = float(float(0.2) + (float(ratio) * float(0.35)))
        new = pd.DataFrame([util])

        self.Y = pd.concat([self.Y, new])

    def add_agent_first_n_bid_to_machine_learning_with_low_utility(self, sorted_bids_agent):

        if self.number_of_goal_of_utility > 150:
            bid_number = 40
        elif self.number_of_goal_of_utility > 100:
            bid_number = int(float(self.number_of_goal_of_utility) / float(3.4))
        elif self.number_of_goal_of_utility > 80:
            bid_number = int(float(self.number_of_goal_of_utility) / float(3.1))
        elif self.number_of_goal_of_utility > 50:
            bid_number = int(float(self.number_of_goal_of_utility) / float(3))
        elif self.number_of_goal_of_utility > 30:
            bid_number = 9
        elif self.number_of_goal_of_utility > 18:
            bid_number = 7
        elif 16 > self.number_of_goal_of_utility > 8:
            bid_number = int(float(self.number_of_goal_of_utility) / float(2))
        else:
            bid_number = 4
        for i in range(0, bid_number + 1):
            bid = sorted_bids_agent[i]
            self.util_add_agent_first_n_bid_to_machine_learning_with_low_utility(bid, float(float(i) / float(bid_number)))

    def is_acceptable(self, bid: Bid, progress):
        util = float(self.profile.getUtility(bid))
        if util >= float(self.reservationBid_utility):
            if util >= 0.94:
                self.acceptance_condition = 1
                return True
            elif util >= 0.91 and 0.76 > float(self.call_model_lgb(bid)) > 0.6:
                self.acceptance_condition = 2
                return True
            elif float(0.85) >= float(progress) > 0.82 and util > self.goal_of_utility - float(0.1) and util - float(0.28) > float(self.call_model_lgb(bid)):
                self.acceptance_condition = 3
                return True
            elif float(0.94) >= float(progress) > 0.85 and util > self.goal_of_utility - float(0.14) and util - float(0.23) > float(self.call_model_lgb(bid)):
                self.acceptance_condition = 4
                return True
            elif float(1.0) >= float(progress) > 0.93 and util > self.goal_of_utility - float(0.2) and util - float(0.18) > float(self.call_model_lgb(bid)):
                self.acceptance_condition = 5
                return True
            elif float(1.0) >= float(progress) > 0.97 and util - float(0.12) > float(self.call_model_lgb(bid)):
                self.acceptance_condition = 6
                return True
        return False

    def find_bid(self, progress_time):
        progress_time = float(progress_time)
        if float(self.my_offered_number_of_time_from_ai) < float(len(self.eva_util_val_acc_to_lgb_m_with_max_bids_for_agent)) * float(2) \
                and ((0 < progress_time < 0.17) or (0.23 < progress_time < 0.37) or (0.45 < progress_time < 0.93) or (
                0.97 < progress_time <= 0.985)) and self.lgb_model is not None \
                and len(self.eva_util_val_acc_to_lgb_m_with_max_bids_for_agent) >= 1:
            index = random.randint(0,
                                   len(self.eva_util_val_acc_to_lgb_m_with_max_bids_for_agent) - 1)
            if float(self.reservationBid_utility) < float(self.profile.getUtility(self.eva_util_val_acc_to_lgb_m_with_max_bids_for_agent[index])):
                self.my_offered_number_of_time_from_ai = self.my_offered_number_of_time_from_ai + 1
                return self.eva_util_val_acc_to_lgb_m_with_max_bids_for_agent[index]
        elif ((0.25 < progress_time < 0.30) or (0.58 < progress_time < 0.64) or (0.82 < progress_time < 0.86) or (
                0.965 < progress_time <= 0.995)) and self.lgb_model is not None and len(
            self.eva_util_val_acc_to_lgb_m_with_max_bids_for_agent) >= 1:
            index = random.randint(0, len(self.eva_util_val_acc_to_lgb_m_with_max_bids_for_agent) - 1)
            if float(self.reservationBid_utility) < float(
                    self.profile.getUtility(self.eva_util_val_acc_to_lgb_m_with_max_bids_for_agent[index])):
                return self.eva_util_val_acc_to_lgb_m_with_max_bids_for_agent[index]
        elif progress_time < 0.4:
            if self.number_of_bid_greater_than95 >= 8:
                index = random.randint(self.number_of_bid_greater_than95 - 4, self.number_of_bid_greater_than95)
                if float(self.reservationBid_utility) < float(self.profile.getUtility(self.sorted_bids_agent[index])):
                    return self.sorted_bids_agent[index]

            elif self.number_of_bid_greater_than95 >= 4:
                index = random.randint(3, self.number_of_bid_greater_than95)
                if float(self.reservationBid_utility) < float(self.profile.getUtility(self.sorted_bids_agent[index])):
                    return self.sorted_bids_agent[index]

            elif self.number_of_bid_greater_than95 >= 1:
                index = random.randint(1, self.number_of_bid_greater_than95)
                if float(self.reservationBid_utility) < float(self.profile.getUtility(self.sorted_bids_agent[index])):
                    return self.sorted_bids_agent[index]

            elif self.number_of_bid_greater_than85 >= 1:
                index = random.randint(1, self.number_of_bid_greater_than85)
                if float(self.reservationBid_utility) < float(self.profile.getUtility(self.sorted_bids_agent[index])):
                    return self.sorted_bids_agent[index]

        elif progress_time < 0.85:
            if self.number_of_bid_greater_than95 > 1 and self.number_of_bid_greater_than85 > 2:
                index = random.randint(self.number_of_bid_greater_than95, self.number_of_bid_greater_than85)
                if float(self.reservationBid_utility) < float(self.profile.getUtility(self.sorted_bids_agent[index])):
                    return self.sorted_bids_agent[index]

            elif self.number_of_bid_greater_than85 >= 1:
                index = random.randint(1, self.number_of_bid_greater_than85)
                if float(self.reservationBid_utility) < float(self.profile.getUtility(self.sorted_bids_agent[index])):
                    return self.sorted_bids_agent[index]

        elif progress_time <= 0.975:
            if self.number_of_goal_of_utility > self.number_of_bid_greater_than85:
                index = random.randint(self.number_of_bid_greater_than85, self.number_of_goal_of_utility)
                if float(self.reservationBid_utility) < float(self.profile.getUtility(self.sorted_bids_agent[index])):
                    return self.sorted_bids_agent[index]
            elif self.number_of_goal_of_utility > self.number_of_bid_greater_than95:
                index = random.randint(self.number_of_bid_greater_than95, self.number_of_goal_of_utility)
                if float(self.reservationBid_utility) < float(self.profile.getUtility(self.sorted_bids_agent[index])):
                    return self.sorted_bids_agent[index]
            elif self.number_of_goal_of_utility > 1:
                index = random.randint(1, self.number_of_goal_of_utility)
                if float(self.reservationBid_utility) < float(self.profile.getUtility(self.sorted_bids_agent[index])):
                    return self.sorted_bids_agent[index]
        elif 0.91 <= progress_time <= 0.995:
            if self.offers_unique_sorted is not None and not len(self.offers_unique_sorted) == 0:
                bid = self.offers_unique_sorted[0]
                util_of_bid = float(self.profile.getUtility(bid))
                if float(self.reservationBid_utility) < float(util_of_bid) and float(util_of_bid) >= float(self.goal_of_utility) - float(0.03) and float(
                        self.call_model_lgb(bid)) < util_of_bid:
                    return bid
        elif float(self.reservationBid_utility) < float(self.profile.getUtility(self.sorted_bids_agent[3])):
            return self.sorted_bids_agent[3]
        return self.sorted_bids_agent[0]
