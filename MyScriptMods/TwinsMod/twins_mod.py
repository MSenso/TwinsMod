import itertools
from functools import wraps

import services
import sims4.commands
import sims4.log
from protocolbuffers import PersistenceBlobs_pb2
from sims.sim import Sim
from sims4.resources import Types, get_resource_key


@sims4.commands.Command('start.debug', command_type=sims4.commands.CommandType.Live)
def start_debugging(_connection=None):
    import pydevd_pycharm
    pydevd_pycharm.settrace('localhost', port=1234, stdoutToServer=True, stderrToServer=True)


def get_parents(sim_info):
    genealogy = sim_info.genealogy
    parent_ids = []
    for parent_id in genealogy.get_parent_sim_ids_gen():
        if parent_id:
            parent_ids.append(parent_id)
    return parent_ids


def add_traits_to_sim(sim_info, trait):
    instance_manager = services.get_instance_manager(Types.TRAIT)
    trait_ghost_anger = instance_manager.get(get_resource_key(trait, Types.TRAIT))
    if not sim_info.has_trait(trait_ghost_anger):
        sim_info.add_trait(trait_ghost_anger)


def add_relbit_to_sims(sim_info, another_sim_info, relbit_id=4127800305):
    bit_manager = services.get_instance_manager(Types.RELATIONSHIP_BIT)
    relbit_twins = bit_manager.get(relbit_id)
    if relbit_twins is None:
        return
    sim_info.relationship_tracker.add_relationship_bit(another_sim_info.id, relbit_twins)
    another_sim_info.relationship_tracker.add_relationship_bit(sim_info.id, relbit_twins)


def check_appearance_similarity(sim_info, another_sim_info):
    actor_facial_attributes = PersistenceBlobs_pb2.BlobSimFacialCustomizationData()
    actor_facial_attributes.MergeFromString(sim_info.facial_attributes)
    target_facial_attributes = PersistenceBlobs_pb2.BlobSimFacialCustomizationData()
    target_facial_attributes.MergeFromString(another_sim_info.facial_attributes)

    total_modifiers = 0
    similar_modifiers = 0

    for actor_modifier, target_modifier in zip(
            itertools.chain(actor_facial_attributes.face_modifiers,  # type: ignore
                            actor_facial_attributes.body_modifiers),  # type: ignore
            itertools.chain(target_facial_attributes.face_modifiers,  # type: ignore
                            target_facial_attributes.body_modifiers)):  # type: ignore
        total_modifiers += 1
        if abs(actor_modifier.amount - target_modifier.amount) <= 0.35:  # 35% tolerance
            similar_modifiers += 1
    return similar_modifiers / total_modifiers


def _on_sim_added(sim_info):
    try:
        days_lived = sim_info.age_progress
        active_sim_parents = set(get_parents(sim_info))
        active_household = services.active_household()
        if active_household is None:
            return
        for another_sim_info in active_household:
            if sim_info is not another_sim_info:
                another_sim_parents = set(get_parents(another_sim_info))
                # Check if they have at least one common parent
                common_parents = active_sim_parents.intersection(another_sim_parents)
                if common_parents:
                    sim_days_lived = another_sim_info.age_progress
                    if sim_info.gender == another_sim_info.gender and \
                            sim_info.age == another_sim_info.age and int(sim_days_lived) == int(days_lived):
                        similarity = check_appearance_similarity(sim_info, another_sim_info)
                        if similarity >= 0.75:
                            add_relbit_to_sims(sim_info, another_sim_info)
    except Exception as e:
        sims4.log.exception("Injection", "Twins Mod Exception", exc=e)


def inject(target_function, new_function):
    @wraps(target_function)
    def _inject(*args, **kwargs):
        return new_function(target_function, *args, **kwargs)

    return _inject


def inject_to(target_object, target_function_name):
    def _inject_to(new_function):
        target_function = getattr(target_object, target_function_name)
        setattr(target_object, target_function_name, inject(target_function, new_function))
        return new_function

    return _inject_to


@inject_to(Sim, 'on_add')
def check_twins(original, self, *args, **kwargs):
    result = original(self, *args, **kwargs)
    try:
        _on_sim_added(self.sim_info)
    except Exception as e:
        sims4.log.exception("Injection", "Twins Mod Exception", exc=f'Error Twins mod: {str(e)}')
    return result
