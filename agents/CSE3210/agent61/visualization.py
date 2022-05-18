import matplotlib.pyplot as plt
import json

dictionary = json.load(open('././results/results_summaries.json', 'r'))

i = 0

for result in dictionary:
    print(result.items())
    agreement = (result["result"] == "agreement")
    print(agreement)
    adding = {'nash_product','social_welfare'}

    xAxis = []
    yAxis = []
    for (key, value) in result.items():
        if adding.__contains__(key):
            xAxis.append(key)
            yAxis.append(value)
        elif 'utility' in key:
            key_new ="agent_"+ key[8:]

            xAxis.append(result[key_new][:len(result[key_new]) - 5] + " utility")
            yAxis.append(value)

    if agreement:
        ## LINE GRAPH ##
        color = 'blue'

        ## BAR GRAPH ##
        fig = plt.figure()
        plt.bar(xAxis, yAxis, alpha=1, color=color, zorder=5)
        plt.grid(figure=fig, zorder=0)
        plt.xlabel('variable')
        plt.ylabel('value')
        plt.show()

        fig.savefig("././results/plots/fig" + str(i) + ".png")
        i = i+1
