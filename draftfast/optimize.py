import random
from typing import List
from draftfast import player_pool as pool
from draftfast.orm import RosterSelect, Roster
from draftfast.optimizer import Optimizer
from draftfast.exposure import check_exposure, \
    get_exposure_table, get_exposure_matrix, get_exposure_args
from draftfast.rules import RuleSet
from draftfast.settings import PlayerPoolSettings, OptimizerSettings
from draftfast.lineup_contraints import LineupConstraints


def run(rule_set: RuleSet,
        player_pool: list,
        optimizer_settings=None,
        player_settings=None,
        exposure_dct=None,
        roster_gen=None,
        verbose=False) -> Roster:
    constraints = LineupConstraints()

    if player_settings and player_settings.banned:
        for name in player_settings.banned:
            constraints.ban(name)

    if player_settings and player_settings.locked:
        for name in player_settings.locked:
            constraints.lock(name)

    players = pool.filter_pool(
        player_pool,
        player_settings,
    )
    optimizer = Optimizer(
        players=players,
        rule_set=rule_set,
        settings=optimizer_settings,
        lineup_constraints=constraints,
        exposure_dct=exposure_dct
    )

    variables = optimizer.variables

    if optimizer.solve():
        if roster_gen:
            roster = roster_gen()
        else:
            roster = RosterSelect().roster_gen(rule_set.league)

        for i, player in enumerate(players):
            if variables[i].solution_value() == 1:
                roster.add_player(player)

        if verbose:
            print('Optimal roster for: {}'.format(rule_set.league))
            print(roster)

        return roster

    if verbose:
        print(
            '''
            No solution found for command line query.
            Try adjusting your query by taking away constraints.

            Active constraints: {}
            Player count: {}
            '''.format(optimizer_settings, len(players or []))
        )
    return None


def run_multi(
    iterations: int,
    rule_set: RuleSet,
    player_pool: list,
    player_settings=PlayerPoolSettings(),
    optimizer_settings=OptimizerSettings(),
    verbose=False,
    exposure_bounds=None,
    exposure_random_seed=None,
) -> [List[Roster], list]:

    # set the random seed globally for random lineup exposure
    if exposure_random_seed:
        random.seed(exposure_random_seed)

    rosters = []
    for _ in range(0, iterations):
        exposure_dct = None
        if exposure_bounds:
            exposure_dct = get_exposure_args(
                existing_rosters=optimizer_settings.existing_rosters,
                exposure_bounds=exposure_bounds,
                n=iterations,
                use_random=bool(exposure_random_seed),
                random_seed=exposure_random_seed,
            )

        roster = run(
            rule_set=rule_set,
            player_pool=player_pool,
            optimizer_settings=optimizer_settings,
            player_settings=player_settings,
            exposure_dct=exposure_dct,
            verbose=verbose,
        )
        if roster:
            optimizer_settings.existing_rosters += [roster]

        if roster:
            rosters.append(roster)
        else:
            break

        # clear ban/lock to reset exposure between iterations
        reset_player_ban_lock(player_pool)

    exposure_diffs = {}

    if rosters and verbose:
        print(get_exposure_table(rosters, exposure_bounds))
        print()
        print(get_exposure_matrix(rosters))
        print()

        exposure_diffs = check_exposure(rosters, exposure_bounds)
        for n, d in exposure_diffs.items():
            if d < 0:
                print('{} is UNDER exposure by {} lineups'.format(n, d))
            else:
                print('{} is OVER exposure by {} lineups'.format(n, d))

    return rosters, exposure_diffs


def reset_player_ban_lock(player_pool):
    for p in player_pool:
        p.ban = False
        p.lock = False
