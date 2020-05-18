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
            tube: vol for tube, vol in zip(tube_block.wells()[8:12], [5, 5, 5, 2])
        }
    }
    mm2 = {
        'volume': 20,
        'components': {
            tube: vol
            for tube, vol in zip(tube_block.wells()[8:15], [8, 5, 1, 2, 2, 1, 1])
        }
    }
    mm3 = {
        'volume': 20,
        'components': {
            tube: vol
            for tube, vol in zip(tube_block.wells()[8:13], [12, 5, 1, 1, 1])
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
