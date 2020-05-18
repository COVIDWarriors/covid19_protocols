from opentrons import protocol_api
from opentrons.drivers.rpi_drivers import gpio
import math
import time

# metadata
metadata = {
    'protocolName': 'S5 Station C Version 1',
    'author': 'Nick <protocols@opentrons.com> & Alex Gasulla',
    'source': 'Custom Protocol Request',
    'apiLevel': '2.1'
}

"""
MM_TYPE must be one of the following:
    Seegene
    Universal
    Universal IDT
"""

################################################
# CHANGE THESE VARIABLES ONLY
################################################
NUM_SAMPLES = 48                    # samples + controls
PREPARE_MASTERMIX = True            # Mastermix preparation is needed?
TRANSFER_MASTERMIX = True           # Mastermix transfer is needed?
TRANSFER_SAMPLES = True             # Transfer samples is needed?
TRANSFER_CONTROLS = False           # Transfer controls is needed?
MM_TYPE = 'Universal IDT'           # Type of mastermix
mastermix_multi_dispense = True     # Allow mastermix multidispense
################################################

temperatura = 4
recycle_tips = False
flow_rate_mix = 7
flow_rate = 4

MMTUBE_LABWARE = '2ml tubes'
MMTUBE_LW_DICT = {
    # Radius of each possible tube
    '2ml tubes': 4
}

def get_mm_height(volume):
    # depending on the volume in tube, get mm fluid height
    height = volume // (3.14 * (MMTUBE_LW_DICT[MMTUBE_LABWARE] ** 2))
    height -= 18
    if height < 5:
        return 0.1
    else:
        return height

def transfer_mastermix(mm_tube, dests, VOLUME_MMIX, p300, p20):
    max_trans_per_asp = 8  #230//(VOLUME_MMIX+5)
    split_ind = [ind for ind in range(0, NUM_SAMPLES, max_trans_per_asp)]
    dest_sets = [dests[split_ind[i]:split_ind[i+1]]
             for i in range(len(split_ind)-1)] + [dests[split_ind[-1]:]]
    pip = p300 if VOLUME_MMIX >= 20 else p20
    # pip.pick_up_tip()
    # get initial fluid height to avoid overflowing mm when aspiring
    mm_volume = VOLUME_MMIX * NUM_SAMPLES
    volume_height = get_mm_height(mm_volume)
    for set in dest_sets:
        # check height and if it is low enought, aim for the bottom
        if volume_height < 5:
            disp_loc = mm_tube.bottom(1)
        else:
            # recalculate volume height
            mm_volume -= VOLUME_MMIX * max_trans_per_asp
            volume_height = get_mm_height(mm_volume)
            disp_loc = mm_tube.bottom(volume_height)
        #pip.aspirate(4, disp_loc)
        pip.distribute(VOLUME_MMIX, disp_loc, [d.bottom(2) for d in set],
                   air_gap=1, disposal_volume=0, new_tip='never')
        pip.blow_out(disp_loc)
    pip.drop_tip(home_after=False)

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
    mm3 = {
        'volume': 20,
        'components': {
            tube: vol
            for tube, vol in zip(
                tube_block.wells()[8:13], [12, 5, 1, 1, 1])
        }
    }

    mm_dict = {
        'seegene': mm1,
        'universal': mm2,
        'universal idt': mm3,
    }

    if PREPARE_MASTERMIX == True:
        ctx.comment('###############################################')
        ctx.comment('Step PREPARING MASTERMIX')
        ctx.comment('###############################################')
        # create mastermix
        current_volume = 0
        for tube, vol in mm_dict[MM_TYPE]['components'].items():
            mm_vol = vol * (NUM_SAMPLES + 5)
            disp_loc = mm_tube.bottom(5) if mm_vol < 50 else mm_tube.top(-5)
            pip = p300 if mm_vol > 20 else p20
            transfer_max = 200 if mm_vol > 20 else 20
            pip.pick_up_tip()
            transfer_num = math.ceil(mm_vol / transfer_max)
            transfer_vol = mm_vol/transfer_num
            for i in range(transfer_num):
                pip.aspirate(volume = transfer_vol, location = tube.bottom(0), rate = flow_rate)
                pip.dispense(volume = transfer_vol, location = disp_loc, rate = flow_rate)
                pip.blow_out()
                current_volume = current_volume + transfer_vol
            if recycle_tips == True:
                pip.return_tip()
            else:
                pip.drop_tip(home_after=False)
        pip.pick_up_tip()
        pip.mix(10, volume = 150, rate = flow_rate_mix, location = mm_tube.bottom(get_mm_height(current_volume)))
        if recycle_tips == True:
            pip.return_tip()
        else:
            pip.drop_tip(home_after=False)

    if TRANSFER_MASTERMIX == True:
        ctx.comment('###############################################')
        ctx.comment('Step TRANSFERING MASTERMIX')
        ctx.comment('###############################################')

        if mastermix_multi_dispense == True:
            # Mastermix is multidispensed (8 in a row) which makes the process faster. It should be used when the plate has no sample only
            p300.pick_up_tip()
            dests = pcr_plate.wells()[:NUM_SAMPLES]
            #mm_dests = [d.bottom(2) for d in sample_dests] #+ pcr_plate.wells()[-2:]]
            transfer_mastermix(mm_tube, dests, mm_dict[MM_TYPE]['volume'], p300, p20)
        else:
            # Mastermix is singledispensed, which makes the process slower. Useful when the plate has sample
            current_volume = mm_dict[MM_TYPE]['volume'] * (NUM_SAMPLES + 5)

            mm_vol = mm_dict[MM_TYPE]['volume']
            mm_dests = [d.bottom(2) for d in sample_dests] #+ pcr_plate.wells()[-2:]]

            for d in mm_dests:
                p20.pick_up_tip()
                p20.aspirate(mm_vol, mm_tube.bottom(get_mm_height(current_volume)))
                p20.dispense(mm_vol, d)
                p20.mix(2, mm_vol)
                p20.blow_out()
                p20.drop_tip(home_after=False)
                current_volume = current_volume - mm_vol

    if TRANSFER_SAMPLES == True:
        ctx.comment('###############################################')
        ctx.comment('Step TRANSFERING SAMPLES')
        ctx.comment('###############################################')
        # transfer samples to corresponding locations
        sample_vol = 5 #25 - mm_vol
        for s, d in zip(sources, sample_dests):
            p20.pick_up_tip()
            #p20.transfer(sample_vol, s.bottom(0.5), d.bottom(0.5), new_tip = 'never')
            p20.aspirate(volume = sample_vol, location = s.bottom(1), rate = flow_rate)
            p20.dispense(volume = sample_vol, location = d.bottom(3), rate = flow_rate)
            p20.mix(2, volume = 10, rate = flow_rate_mix, location = d.bottom(1))
            #p20.blow_out(d.top(-2))
            #p20.aspirate(sample_vol, d.top(2))
            p20.drop_tip(home_after=False)

    if TRANSFER_CONTROLS == True:
        ctx.comment('###############################################')
        ctx.comment('Step TRANSFERING CONTROLS')
        ctx.comment('###############################################')
        # transfer positive and negative controls
        for s, d in zip(tube_block.wells()[1:3], pcr_plate.wells()[-2:]):
            p20.pick_up_tip()
            p20.transfer(sample_vol, s.bottom(2), d.bottom(2), new_tip = 'never')
            p20.mix(1, 10, d.bottom(2))
            p20.blow_out(d.top(-2))
            p20.aspirate(5, d.top(2))
            p20.drop_tip()

    # Send robot home
    ctx.comment(' ')
    ctx.comment('###############################################')
    ctx.comment('Homing robot')
    ctx.comment('###############################################')
    ctx.comment(' ')
    ctx.home()
###############################################################################
    # Light flash end of program
    import os
    #os.system('mpg123 /etc/audio/speaker-test.mp3')
    for i in range(3):
        gpio.set_rail_lights(False)
        gpio.set_button_light(1,0,0)
        time.sleep(0.3)
        gpio.set_rail_lights(True)
        gpio.set_button_light(0,0,1)
        time.sleep(0.3)
    gpio.set_button_light(0,1,0)
    ctx.comment('Finished!')
