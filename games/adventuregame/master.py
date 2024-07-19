from typing import List, Dict, Tuple

from backends import Model
from clemgame import file_utils
# from clemgame import metrics
import clemgame.metrics as metrics
from clemgame.clemgame import GameMaster, GameBenchmark, GameScorer, DialogueGameMaster, Player
from clemgame import get_logger

import numpy as np

from games.adventuregame.if_wrapper import BasicIFInterpreter

import re

GAME_NAME = "adventuregame"
logger = get_logger(__name__)


class AdventureGameMaster(DialogueGameMaster):
    """
    DialogueGameMaster subclass for adventuregame.
    """
    def __init__(self, experiment: Dict, player_models: List[Model]):
        super().__init__(GAME_NAME, experiment, player_models)
        # self.experiment = experiment
        # self.game = None
        # self.game_instance = None

        self.turns = []
        self.success = True

        self.invalid_format: str = ""  # to track responses with invalid format

        self.finished: bool = False  # game finished successfully

    def _on_setup(self, **game_instance):
        self.game_instance = game_instance  # fetch game parameters here
        # print("game_instance type:", type(game_instance))

        # check game variant:
        self.if_variant = self.game_instance['variant']

        # initialize IF interpreter:
        self.if_interpreter = BasicIFInterpreter(self.game_instance)

        # TODO: put all interpreter-relevant data into instances
        # TODO: use clemgame resource loading

        # create player:
        self.player = Player(self.player_models[0])

        # Add the players: these will be logged to the records interactions.json
        # Note: During game play the players will be called in the order added here
        self.add_player(self.player)

        # keep history of plans:
        if self.if_variant == 'plan':
            self.plan_history: list = list()

        self.goals_required = set(self.game_instance['goal_state'])
        self.goals_required_cnt = len(self.goals_required)
        self.goals_achieved = set()

        # TODO: use 'optimal_turns'
        # TODO: log scoring-relevant instance values to be retrieved by GameScorer

        adventure_info: dict = {"variant": self.game_instance['variant'], "max_turns": self.game_instance['max_turns'],
                                "optimal_turns": self.game_instance['optimal_turns'],
                                "goal_count": self.goals_required_cnt}
        # self.log_to_self("adventure_info", adventure_info)
        self.log_key("adventure_info", adventure_info)

    def _on_before_game(self):
        # get initial room description from IF interpreter:
        initial_room_desc = self.if_interpreter.get_full_room_desc()

        first_message = self.game_instance["prompt"] + initial_room_desc

        # Do something before the game start e.g. add the initial prompts to the message list for the players
        # self.add_user_message(self.player, self.game_instance["prompt"])
        self.add_user_message(self.player, first_message)

        # print(self.messages_by_names[self.player.descriptor])
        # print(self.get_players())

    def _validate_player_response(self, player: Player, utterance: str) -> bool:
        # Check responses for specific players
        # TODO?: reprompting? -> different from IF action processing responses?
        # TODO: check if invalid responses are recorded for inspection if this returns False
        if player == self.player:
            # Check rule: utterance starts with IF >
            if not utterance.startswith(">"):
                self.success = False
                self.invalid_format = "command_tag_missing"
                # return True
                return False
            if self.if_variant == 'plan':
                if "\nNext actions:" not in utterance:
                    self.success = False
                    self.invalid_format = "next_actions_missing"
                    # return True
                    return False
        return True

    def _on_parse_response(self, player: Player, utterance: str) -> Tuple[str, bool]:
        """
        Hook

        Decide if a response utterance should be modified. If not simply return the utterance.

        When a modified utterance and a true value is returned, then a 'parse' event is logged.

        :param player: that produced the response
        :param utterance: to be potentially modified
        :return: the (modified) utterance and if to log the parse action (default: True)
        """
        if self.if_variant == 'plan':
            new_plan = utterance.split("\nNext actions:")[1]
            self.plan_history.append(new_plan)
            # print(self.plan_history)
            # TODO: set up limited plan feedback by removing plans here and feeding them back into messages by args
            # TODO: log plans

        return utterance, True

    def _does_game_proceed(self) -> bool:
        """
        Template method: must be implemented
        """
        # if self.success == False:
        #    return False

        if self.invalid_format:
            self.log_to_self("invalid_format", self.invalid_format)
            return False

        # stop game when all goal states have been achieved:
        if self.goals_achieved == self.goals_required:
            self.finished = True
            self.log_to_self("adventure_finished", list(self.goals_achieved))
            return False

        # stop game when turn limit is reached:
        if len(self.turns) >= self.game_instance['max_turns']:
            self.log_to_self("turn_limit_reached", self.game_instance['max_turns'])
            return False
        return True

    def _on_after_turn(self, turn_idx: int):
        """
        Play loop hook: Called after all players have been prompted and their responses have been parsed+validated.
        """
        # print("_on_after_turn call starts")

        if self._does_game_proceed():  # only pass last message to IF if the game is still going
            # IF INTERACTION
            # get the last player action:
            # print("Player messages:", self.messages_by_names[self.player.descriptor])
            last_action: str = self.messages_by_names[self.player.descriptor][-1]['content']
            # print("Last player message:", last_action)
            # strip player action to IF input:
            # if_input: str = last_action[1:].strip()
            if_input: str = last_action[1:].split("\n")[0].strip()
            # print("Stripped IF input:", if_input)

            # count achieved goals:
            prior_goal_count = len(self.goals_achieved)
            # IF interpreter returns set of achieved goal states in string form:
            goals_achieved, if_response, fail = self.if_interpreter.process_action(if_input)
            # TODO?: return concise success info?

            # TODO: make fails log so that they show up in transcript
            if fail:
                self.log_to_self("action_fail", fail)
                self.log_message_to_self(f"action_fail: {str(fail)}")

            self.goals_achieved = goals_achieved
            # count goals achieved this turn:
            post_goal_count = len(self.goals_achieved)
            turn_score = post_goal_count - prior_goal_count
            # print("turn score:", turn_score)

            # TODO?: expose more detailed goal status?

            goal_status = {"goal_states_achieved": list(self.goals_achieved), "turn_goal_score": turn_score}
            self.log_to_self("goal_status", goal_status)
            self.log_message_to_self(f"goal_status: {str(goal_status)}")

            # add IF response to dialog:
            self.add_user_message(self.player, if_response)

            # record successful turn:
            self.turns.append(self.success)

        # print("_on_after_turn call ends")

    def _on_after_game(self):
        game_result = {"goal_states_achieved": list(self.goals_achieved), "game_successfully_finished": self.finished}
        self.log_to_self("game_result", game_result)


class AdventureGameScorer(GameScorer):
    def __init__(self, name: str, experiment: Dict, game_instance: Dict):
        super().__init__(name, experiment, game_instance)

    def compute_scores(self, episode_interactions: Dict) -> None:
        """ Episode level scores"""
        adventure_info: dict = dict()
        turn_scores = []
        # IF interpreter interaction fail phases/types; first two must be 'parsing' and 'resolution' phases:
        fail_types = ['parsing', 'resolution', 'lark_exception', 'undefined_action_verb', 'undefined_action',
                      'undefined_repr_str', 'undefined_type', 'not_room_type', 'no_exit_to', 'multiple_exits_to',
                      'entity_not_accessible', 'multiple_entity_ambiguity', 'pre_state_mismatch']
        turn_fails = []
        invalid_format: str = ""
        turn_limit_loss: bool = False
        successfully_finished = False
        final_goals_achieved: list = list()
        for turn_idx, turn in enumerate(episode_interactions["turns"]):
            turn_score = {"request_count": 1}  # only one request per turn for now: reprompting pending
            turn_fail = {fail_type: 0 for fail_type in fail_types}
            for event in turn:
                action = event["action"]

                if action["type"] == "adventure_info":
                    adventure_info = action['content']

                if action["type"] == "invalid_format":
                    invalid_format = action['content']

                if action["type"] == "action_fail":
                    # record IF interaction fail phase:
                    turn_fail[action['content']['phase']] = 1
                    # record IF interaction fail type:
                    turn_fail[action['content']['fail_type']] = 1

                if action["type"] == "turn_limit_reached":
                    turn_limit_loss = True

                if action["type"] == "goal_status":
                    turn_score["goal_score"] = action['content']['turn_goal_score']

                if action["type"] == "game_result":
                    successfully_finished = action['content']['game_successfully_finished']
                    final_goals_achieved = action['content']['goal_states_achieved']

            if invalid_format:
                turn_score["violated_request_count"] = 1
                turn_score["parsed_request_count"] = 0
            else:
                turn_score["violated_request_count"] = 0
                turn_score["parsed_request_count"] = 1
            # standard turn-level request scores:
            self.log_turn_score(turn_idx, metrics.METRIC_REQUEST_COUNT, turn_score["request_count"])
            self.log_turn_score(turn_idx, metrics.METRIC_REQUEST_COUNT_PARSED, turn_score["parsed_request_count"])
            self.log_turn_score(turn_idx, metrics.METRIC_REQUEST_COUNT_VIOLATED, turn_score["violated_request_count"])
            # invalid format type:
            if invalid_format == "command_tag_missing":
                self.log_turn_score(turn_idx, 'command_tag_missing', 1)
                self.log_turn_score(turn_idx, 'next_actions_missing', 0)
            elif invalid_format == "next_actions_missing":
                self.log_turn_score(turn_idx, 'command_tag_missing', 0)
                self.log_turn_score(turn_idx, 'next_actions_missing', 1)
            else:
                self.log_turn_score(turn_idx, 'command_tag_missing', 0)
                self.log_turn_score(turn_idx, 'next_actions_missing', 0)
            # IF interaction fails:
            self.log_turn_score(turn_idx, 'action_parsing_fail', turn_fail["parsing"])
            self.log_turn_score(turn_idx, 'action_resolution_fail', turn_fail["resolution"])
            for fail_type in fail_types[2:]:
                self.log_turn_score(turn_idx, fail_type, turn_fail[fail_type])
            # turn-level goal score:
            self.log_turn_score(turn_idx, 'goal_score', turn_score["goal_score"])

            turn_scores.append(turn_score)
            turn_fails.append(turn_fail)

        # standard episode-level request scores:
        violated_request_count = sum([turn["violated_request_count"] for turn in turn_scores])
        self.log_episode_score(metrics.METRIC_REQUEST_COUNT_VIOLATED, violated_request_count)

        parsed_request_count = sum([turn["parsed_request_count"] for turn in turn_scores])
        self.log_episode_score(metrics.METRIC_REQUEST_COUNT_PARSED, parsed_request_count)

        request_count = sum([turn["request_count"] for turn in turn_scores])
        self.log_episode_score(metrics.METRIC_REQUEST_COUNT, request_count)

        self.log_episode_score(metrics.METRIC_REQUEST_SUCCESS, parsed_request_count / request_count)

        # episode-level action fail scores:
        action_parsing_fail_count = sum([turn["parsing"] for turn in turn_fails])
        self.log_episode_score('action_parsing_fail', action_parsing_fail_count)

        action_resolution_fail_count = sum([turn["resolution"] for turn in turn_fails])
        self.log_episode_score('action_resolution_fail', action_resolution_fail_count)

        for fail_type in fail_types[2:]:
            type_fail_count = sum([turn[fail_type] for turn in turn_fails])
            self.log_episode_score(fail_type, type_fail_count)

        # record turn limit exceeding loss:
        if turn_limit_loss:
            self.log_episode_score("turn_limit_loss", 1)
        else:
            self.log_episode_score("turn_limit_loss", 0)

        # turn count for metrics based on it:
        turn_count: int = len(turn_scores)

        # get optimal turns for this episode:
        # TODO: read from episode key
        optimal_turns: int = adventure_info['optimal_turns']
        # 'on par' score:
        turns_over_par: int = turn_count - optimal_turns
        if successfully_finished:
            self.log_episode_score("turns_over_par", turns_over_par)
        else:
            self.log_episode_score("turns_over_par", np.nan)

        # range of possible number of turns:
        turn_range = adventure_info['max_turns'] - adventure_info['optimal_turns']
        # ratio of turns taken / possible turn range:
        turn_ratio = 1 - turns_over_par / turn_range
        if successfully_finished:
            self.log_episode_score("turn_ratio", turn_ratio)
        else:
            self.log_episode_score("turn_ratio", np.nan)

        # get final score:
        # final_goal_score = turn_scores[-1]["goal_score"]
        final_goal_score = len(final_goals_achieved)

        goal_count: int = adventure_info['goal_count']
        achieved_ratio = final_goal_score / goal_count
        self.log_episode_score("achieved_goal_ratio", achieved_ratio)

        # get goal achievement rating:
        goal_rating = final_goal_score / len(turn_scores)

        # log goal rating as main score:
        # self.log_episode_score(metrics.BENCH_SCORE, np.nan)
        # self.log_episode_score(metrics.BENCH_SCORE, goal_rating)

        # combine goals/turns into overall rating:
        full_rating = achieved_ratio * turn_ratio

        # log full rating as main score:
        # self.log_episode_score(metrics.BENCH_SCORE, np.nan)
        if successfully_finished:
            self.log_episode_score(metrics.BENCH_SCORE, full_rating)
        else:
            self.log_episode_score(metrics.BENCH_SCORE, np.nan)

        # invalid format aborted:
        # TODO: handle different types of format aborts for planning variant
        if invalid_format:
            self.log_episode_score(metrics.METRIC_ABORTED, 1)
        else:
            self.log_episode_score(metrics.METRIC_ABORTED, 0)

        # log successful/failed play:
        if successfully_finished:
            self.log_episode_score(metrics.METRIC_SUCCESS, 1)
            self.log_episode_score(metrics.METRIC_LOSE, 0)
        else:
            self.log_episode_score(metrics.METRIC_SUCCESS, 0)
            self.log_episode_score(metrics.METRIC_LOSE, 1)


class AdventureGameBenchmark(GameBenchmark):
    def __init__(self):
        super().__init__(GAME_NAME)

    def get_description(self):
        return "Text adventure game"

    def create_game_master(self, experiment: Dict, player_models: List[Model]) -> GameMaster:
        return AdventureGameMaster(experiment, player_models)

    def create_game_scorer(self, experiment: Dict, game_instance: Dict) -> GameScorer:
        return AdventureGameScorer(GAME_NAME, experiment, game_instance)