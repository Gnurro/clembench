import argparse
import pandas as pd 
import json

# default list of games
games = ['imagegame', 'privateshared', 'taboo', 'matchit_ascii'] # instances_v1.6.json
# games = ['wordle', 'wordle_withclue', 'wordle_withcritic'] # no instances v2.0 (or v1.6?)
# games = ['referencegame'] # instances_v1.6_en.json
# games = ['matchit', 'codenames'] # instances_v1_6.json
# games = ['textmapworld_graphreasoning', 'textmapworld_main', 'textmapworld_specificroom'] # instances_v1.6.json, -p textmapworld/


# collection of which entries of the instance files should be compared per game
target_dict = {
    "imagegame": "target_grid",
    "privateshared": "slots",
    "referencegame": ["player_1_target_grid", "player_1_second_grid", "player_1_third_grid"], # Or is the order of grids also relevant?
    "taboo": "target_word",
    "wordle": "target_word",
    "wordle_withclue": "target_word",
    "wordle_withcritic": "target_word",
    "codenames": "assignments", # use special treatment!
    "matchit": ["image_a", "image_b"],
    "matchit_ascii": ["grid_a", "grid_b"],
    "textmapworld_graphreasoning": ["Current_Position", "Picture_Name"],
    "textmapworld_main": ["Current_Position", "Picture_Name"],
    "textmapworld_specificroom": ["Current_Position", "Picture_Name", "Specific_Room"]
}


def check_overlap(games: list, path_to_games: str, to_compare: list, print_output: bool = False):
    for game in games:
        target = target_dict[game]
        dfs = tuple()

        for version in to_compare:
            targets = []
            epids = []
            instance_path = path_to_games + game + "/in/" + version
            
            with open(instance_path) as f:
                instances = json.load(f)
            for experiment in instances["experiments"]:
                for instance in experiment["game_instances"]:
                    epids.append(experiment["name"] + "_" + str(instance["game_id"]))
                    if isinstance(target, list):
                        this_target = " ".join([instance[t] for t in target])
                    else:
                        this_target = instance[target]
                        if isinstance(this_target, dict):
                            if game == "codenames":
                                this_target = special_codenames_treatment(this_target)
                            else:
                                this_target = str(this_target)
                        elif isinstance(this_target, list):
                            this_target = " ".join(this_target)
                            
                    targets.append(this_target)
                
            df = pd.DataFrame({
                "epid": epids,
                "target": targets
            })
            dfs += (df,)

        overlap = pd.merge(dfs[0], dfs[1], how = "inner", on = "target")
        print(f"{len(overlap)} instance(s) overlap in {game} between {to_compare[0]} and {to_compare[1]}")
        if print_output and len(overlap) > 0:
            print(overlap[["epid_x", "epid_y"]])

def special_codenames_treatment(assignments : dict)-> str: 
    """
    Returns the assignments of the codenames board sorted alphabetically as one string.
    """
    assignment_list = []
    for group, words in assignments.items():
        assignment_list += [group]
        assignment_list += sorted(words)
    return str(assignment_list)

if __name__ == '__main__':

    """
    Usage:
    python check_instance_overlap.py -g matchit_ascii -i instances.json instances_v1.6.json
    """

    parser = argparse.ArgumentParser()
    parser.add_argument("--game", "-g", help = "Specify which game you would like to compare.", type = str, default = "")
    parser.add_argument("--instancefile","-i",help = "Specify which instance files you would like to compare",  type = str, nargs = 2)
    parser.add_argument("--path", "-p", help = "Path to the directory where the game can be found, e.g. textmapworld/", type = str, default = "")
    parser.add_argument("--print_output", "-o", help = "Print overlapping instances if there are any.", type = bool, default = False)
    args = parser.parse_args()
    
    game = args.game
    to_compare = args.instancefile
    path = args.path
    print_output = args.print_output

    if game:
        games = [game]
    print(" ######## Checking ########")
    check_overlap(games, path, to_compare, print_output)