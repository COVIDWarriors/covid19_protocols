from opentrons import protocol_api
from opentrons.drivers.rpi_drivers import gpio
import math

# metadata
metadata = {
    'protocolName': 'S5 Station C Version 1',
    'author': 'Nick <protocols@opentrons.com>',
    'source': 'Custom Protocol Request',
    'apiLevel': '2.1'
}

"""
MM_TYPE must be one of the following:
    Seegene
    Universal
"""

NUM_SAMPLES = 16
PREPARE_MASTERMIX = True
MM_TYPE = 'Universal'
temperatura = 4


def run(ctx: protocol_api.ProtocolContext):
    global MM_TYPE

    #Change light to red
    gpio.set_button_light(1,0,0)

    # check source (elution) labware type
    source_plate = ctx.load_labware(
        'biorad_96_alum', '1',
        'chilled elution plate on block from Station B')
    tips20 = [
        ctx.load_labware('opentrons_96_filtertiprack_20ul', slot)
        for slot in ['3', '6', '9']
    ]
    tips300 = [ctx.load_labware('opentrons_96_filtertiprack_200ul', '2')]
    tempdeck = ctx.load_module('tempdeck', '4')
    pcr_plate = tempdeck.load_labware(
        'biorad_96_alum', 'PCR plate')
    tempdeck.set_temperature(temperatura)
    tube_block = ctx.load_labware(
        'tecan_24_wellplate_2000ul', '5',
        '2ml screw tube aluminum block for mastermix + controls')

    # pipette
    p20 = ctx.load_instrument('p20_single_gen2', 'right', tip_racks=tips20)
    p300 = ctx.load_instrument('p300_single_gen2', 'left', tip_racks=tips300)

    # setup up sample sources and destinations
    sources = source_plate.wells()[:NUM_SAMPLES]
    sample_dests = pcr_plate.wells()[:NUM_SAMPLES]

    """ mastermix component maps """
    MM_TYPE = MM_TYPE.lower().strip()
    mm_tube = tube_block.wells()[0]
    mm1 = {
        'volume': 17,
        'components': {
            tube: vol
            for tube, vol in zip(tube_block.wells()[8:12], [5, 5, 5, 2])
        }
    }
    mm2 = {
        'volume': 20,
        'components': {
            tube: vol
            for tube, vol in zip(
                tube_block.wells()[8:15], [8, 5, 1, 2, 2, 1, 1])
        }
    }

    mm_dict = {
        'seegene': mm1,
        'universal': mm2,
    }

    if PREPARE_MASTERMIX:
        # create mastermix
        for tube, vol in mm_dict[MM_TYPE]['components'].items():
            mm_vol = vol * (NUM_SAMPLES + 5)
            disp_loc = mm_tube.bottom(5) if mm_vol < 50 else mm_tube.top(-5)
            pip = p300 if mm_vol > 20 else p20
            transfer_max = 200 if mm_vol > 20 else 20
            pip.pick_up_tip()
            transfer_num = math.ceil(mm_vol/transfer_max)
            transfer_vol = mm_vol/transfer_num
            for i in range(transfer_num):
                pip.aspirate(transfer_vol, tube.bottom(0.2))
                pip.dispense(transfer_vol, disp_loc)
                pip.blow_out()
            pip.mix(3, mm_vol)
            pip.drop_tip(home_after=False)

    # transfer mastermix
    current_volume = mm_dict[MM_TYPE]['volume'] * (NUM_SAMPLES + 5)
    max_vol = 2000 #uL Tube capacity
    max_height = 35 #mm

    mm_vol = mm_dict[MM_TYPE]['volume']
    mm_dests = [d.bottom(2) for d in sample_dests] #+ pcr_plate.wells()[-2:]]
    #p20.transfer(mm_vol, mm_tube.bottom(-3), mm_dests)

    for d in mm_dests:
        height = math.floor(max_height*current_volume//max_vol)
        p20.pick_up_tip()
        p20.aspirate(mm_vol, mm_tube.bottom(height))
        p20.dispense(mm_vol, d)
        p20.mix(2, mm_vol)
        p20.blow_out()
        p20.drop_tip(home_after=False)
        current_volume = current_volume - mm_vol


    # transfer samples to corresponding locations
    #sample_vol = 25 - mm_vol
    #for s, d in zip(sources, sample_dests):
    #    p20.pick_up_tip()
    #    p20.transfer(sample_vol, s.bottom(2), d.bottom(2), new_tip='never')
    #    p20.mix(1, 10, d.bottom(2))
    #    p20.blow_out(d.top(-2))
    #    p20.aspirate(5, d.top(2))
    #    p20.drop_tip(home_after=False)

    # transfer positive and negative controls
    # for s, d in zip(tube_block.wells()[1:3], pcr_plate.wells()[-2:]):
    #    p20.pick_up_tip()
    #    p20.transfer(sample_vol, s.bottom(2), d.bottom(2), new_tip='never')
    #    p20.mix(1, 10, d.bottom(2))
    #    p20.blow_out(d.top(-2))
    #    p20.aspirate(5, d.top(2))
    #    p20.drop_tip()

    #Change light to red
    gpio.set_button_light(0,1,0)
