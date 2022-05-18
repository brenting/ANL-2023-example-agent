import curses
import itertools
import os
import random
import time
from multiprocessing import Process, Manager

from Group18_NegotiationAssignment_Agent import Group18_NegotiationAssignment_Agent
from utils.runners import run_tournament

from Group18_NegotiationAssignment_Project.Group18_NegotiationAssignment_Agent.ranker import *

class AgentProcess:
    def __init__(self, id, process, return_dict):
        self.id = id
        self.process = process
        self.return_dict = return_dict
        return_dict[f"status_{self.id}"] = self.get_starting()

    def get_score(self):
        return return_dict[f"score_{self.id}"]

    def get_status(self):
        return return_dict[f"status_{self.id}"]

    @staticmethod
    def get_finished():
        return f"Process --: finished!"

    @staticmethod
    def get_starting():
        return f"Process --: starting process..."

    @staticmethod
    def get_waiting():
        return f"Process --: waiting for process..."

    def start(self):
        return self.process.start()

    def join(self):
        return self.process.join()

    def is_alive(self):
        return self.process.is_alive()


class HiddenPrints:
    def __enter__(self):
        self._original_stdout = sys.stdout
        sys.stdout = open(os.devnull, 'w')

    def __exit__(self, exc_type, exc_val, exc_tb):
        sys.stdout.close()
        sys.stdout = self._original_stdout


def mutant_filename(i, my_agent):
    split_agent_string = my_agent.split('.')
    split_agent_string[2] = split_agent_string[2] + f"_calibration_temp_{i}"
    return '.'.join(split_agent_string)


def agent_worker(i, my_file, my_agent, deadline_rounds, sample_size, num_domains, agent_pool, domains, thresholds,
                 counter, start, return_dict):
    proc_num = i + 1
    start_agent = time.time()
    out = open(my_file[:len(my_file) - 3] + f"_calibration_temp_{i}.py", 'w')
    with open(my_file, "r") as f:
        lines = f.readlines()
        for index, line in enumerate(lines):
            if "self.thresholds: [float] = [" in line:
                lines[index] = f"        self.thresholds: [float] = {thresholds[i]}\n"
                break
        out.writelines(lines)
    out.close()
    new_agent = mutant_filename(i, my_agent)
    results = []
    agent_iter = itertools.cycle(agent_pool)
    for j in range(sample_size):
        pick = [new_agent, next(agent_iter)]
        settings = {
            "agents": pick,
            "profile_sets": random.sample(domains, k=num_domains),
            "deadline_rounds": deadline_rounds,
        }
        with HiddenPrints():
            results_trace, results_summary = run_tournament(settings, new_agent, verbose=False)
        results.append(results_summary)
        # add the result of the process to the return data structure
        return_dict[f"status_{i}"] = \
            f"Thresholds {int(proc_num):-2}: [{''.join(['=' if k <= j else '_' for k in range(sample_size)])}] |" \
            f" process runtime: {int(time.time() - start_agent):-3}s"
    return_dict[f"status_{i}"] = AgentProcess.get_finished()
    score = metric(results)
    return_dict[f"score_{i}"] = score[new_agent.split('.')[-1]]


def report_progress(stdscr, outs):
    stdscr.clear()
    # If the programme crashes with "_curses.error: addwstr() returned ERR", resize the console bigger
    for n, out in enumerate(outs):
        stdscr.addstr(n, 0, out)
    stdscr.refresh()


def refresh_console_output(stdscr, active_processes, num_processes_left, num_total, epoch, number_of_epochs):
    output = [f"[Epoch {epoch+1} / {number_of_epochs}] Processes [remaining/active/finished/total]: "
              f"[{num_processes_left}/{len(active_processes)}/{num_total - num_processes_left - len(active_processes)}/{num_total}]"]
    for id, process in enumerate(active_processes):
        try:
            if process:
                output.append(process.get_status())
            else:
                raise KeyError
        except KeyError:
            output.append(AgentProcess.get_waiting())
    output.append(f"Overall runtime: {int(time.time() - start):-3}s")
    report_progress(stdscr, output)


def pick_thresholds(number_of_agents, reff):
    thresholds = []
    number_of_thresholds = len(reff.thresholds)
    for _ in range(number_of_agents):
        temp = []
        i = 0
        while len(temp) != number_of_thresholds:
            pick = random.uniform(reff.threshold_checks[i][0], reff.threshold_checks[i][1])
            temp.append(pick)
            i += 1
        thresholds.append(temp)
    return thresholds


if __name__ == '__main__':
    # create results directory if it does not exist
    if not os.path.exists("results"):
        os.mkdir("results")

    agent_pool = {
        "Shreker": "agents.shreker.shreker.Shreker",
        "AveragedTitForTat": "agents.averaged_tit_for_tat_agent.averaged_tit_for_tat_agent.AveragedTitForTat",
        "TradeOffAgent": "agents.trade_off_agent.trade_off_agent.TradeOffAgent",
        "SocialWelfareAgent": "agents.social_welfare_agent.social_welfare_agent.SocialWelfareAgent",
        "BoulwareAgent": "agents.boulware_agent.boulware_agent.BoulwareAgent",
        "ConcederAgent": "agents.conceder_agent.conceder_agent.ConcederAgent",
        "HardlinerAgent": "agents.hardliner_agent.hardliner_agent.HardlinerAgent",
        "ConcedeOneAgent": "agents.concede_one_agent.concede_one_agent.ConcedeOneAgent",
        "LinearAgent": "agents.linear_agent.linear_agent.LinearAgent",
        "RandomAgent": "agents.random_agent.random_agent.RandomAgent",
        "TimeDependentAgent": "agents.time_dependent_agent.time_dependent_agent.TimeDependentAgent",
        "AgreeableAgent": "agents.agreeable_agent.agreeable_agent.AgreeableAgent"
    }
    domains = [
        ["domains/domain00/profileA.json", "domains/domain00/profileB.json"],
        ["domains/domain01/profileA.json", "domains/domain01/profileB.json"],
        ["domains/domain02/profileA.json", "domains/domain02/profileB.json"],
        ["domains/domain03/profileA.json", "domains/domain03/profileB.json"],
        ["domains/domain04/profileA.json", "domains/domain04/profileB.json"],
        ["domains/domain05/profileA.json", "domains/domain05/profileB.json"],
        ["domains/domain06/profileA.json", "domains/domain06/profileB.json"],
        ["domains/domain07/profileA.json", "domains/domain07/profileB.json"],
        ["domains/domain08/profileA.json", "domains/domain08/profileB.json"],
        ["domains/domain09/profileA.json", "domains/domain09/profileB.json"],
    ]
    sample_size = 50  # How many times to run your agent against another random agent in several random domains
    number_of_agents = 20  # How many times to generate random thresholds for your agent
    max_num_processes = 10  # How many processes to run at once
    num_domains = 10  # How many unique domains within which to run the agents.
    number_of_epochs = 5  # How many epochs between sets of agents will take place
    # All data needed to create an agent mutant
    deadline_rounds = 100
    references = {
        "agents.shreker.shreker.Shreker": [Group18_NegotiationAssignment_Agent(), "agents/shreker/shreker.py"],
    }

    counter = 1
    start = time.time()
    manager = Manager()
    return_dict = manager.dict()  # For getting scores out of the processes
    results = None

    # Displaying multiline output
    stdscr = curses.initscr()
    curses.noecho()
    curses.cbreak()
    # Iterate over all epochs
    for epoch in range(number_of_epochs):
        # Fill process queue with all processes
        process_queue = []
        ranking = dict()
        id_to_agent = dict()

        for index, my_agent in enumerate(references):
            thresholds = pick_thresholds(len(references) * number_of_agents, references[my_agent][0])
            for n in range(number_of_agents):
                id_to_agent[index * number_of_agents + n] = mutant_filename(index * number_of_agents + n, my_agent)
                python_process = Process(
                    target=agent_worker,
                    args=(index * number_of_agents + n, references[my_agent][1], my_agent, deadline_rounds, sample_size,
                          num_domains, list(agent_pool.values()), domains, thresholds, counter, start, return_dict)
                )
                agent_process = AgentProcess(index * number_of_agents + n, python_process, return_dict)
                process_queue.append(agent_process)

        active_processes = np.empty(np.min([max_num_processes, len(references) * number_of_agents]), dtype=Process)
        process_queue.reverse()
        processes = []
        while len(process_queue) != 0 or any(map(lambda p: not p or p.is_alive(), active_processes)):
            refresh_console_output(stdscr, active_processes, len(process_queue), number_of_agents, epoch, number_of_epochs)
            for i in range(10):
                time.sleep(0.5)
                if len(process_queue) != 0:
                    for i in range(len(active_processes)):
                        if not active_processes[i] or not active_processes[i].is_alive():
                            next_process = process_queue.pop()
                            next_process.start()
                            active_processes[i] = next_process
                            processes.append(next_process)
                            break
        for process in processes:
            ranking[id_to_agent[process.id]] = process.get_score()
        # Prepare agent pool for the next epoch by replacing with calibrated agents
        results = sorted([agent for agent in ranking], key=lambda agent: ranking[agent])[:10]
        visited = []
        for agent in results:
            if agent in visited:
                continue
            temp = agent.split('.')
            my_file = '/'.join(temp[:-1]) + '.py'
            out = open(temp[0] + '/' + temp[1] + f"/{temp[-1]}_calibration_saved_epoch_{epoch}.py", 'w')
            with open(my_file, "r") as f:
                lines = f.readlines()
                out.writelines(lines)
            out.close()
            temp[-2] = f"{temp[-1]}_calibration_saved_epoch_{epoch}"
            agent_pool[agent.split('.')[-1]] = '.'.join(temp)
            visited.append(agent)

    curses.echo()
    curses.nocbreak()
    curses.endwin()

    print(f"Total time taken: {int(time.time() - start):-3}s")
    # Pick the top 10 scores
    time_str = time.strftime("%Y%m%d-%H%M%S")
    w = open(f"metric_{time_str}.log", "w")
    w.write(f"Top 10 metric agents: \n")
    [w.write(str(tup) + "\n") for tup in results]
    w.close()
