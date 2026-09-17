# =========================================================================
# MODULE: render — node setups
# =========================================================================
"""PS1 material node setups.

Pure data. A dict keyed by PS1 blend mode, each entry holding the node
definitions and link connections for that mode.

Consumed by NFR_PS1MaterialSetup.build_setup() in
render/material_setup.py (extracted in a later batch).
"""

NFR_PS1_NODE_SETUPS = {
    'ADDITIVE': {
        'nodes': [
            ('ShaderNodeOutputMaterial', 'Material Output', (210, 125), 140.0, {'is_active_output': True}),
            ('ShaderNodeAttribute', 'Attribute', (-800, -150), 140.0, {'attribute_name': 'Color'}),
            ('ShaderNodeMath', 'Compare Alpha', (-470, 215), 140.0, {'operation': 'LESS_THAN', 'inputs[1].default_value': 0.999}),
            ('ShaderNodeMixRGB', 'Solid Mix', (-600, -90), 140.0, {'blend_type': 'MULTIPLY', 'inputs[0].default_value': 1.0}),
            ('ShaderNodeMixRGB', 'Solid Multiply 4x', (-470, -110), 140.0, {'blend_type': 'MULTIPLY', 'inputs[0].default_value': 1.0, 'inputs[2].default_value': (4.0, 4.0, 4.0, 1.0)}),
            ('ShaderNodeInvert', 'Solid Invert', (-470, -45), 140.0, {'inputs[0].default_value': 1.0}),
            ('ShaderNodeBsdfTransparent', 'Solid Transparent BSDF', (-470, -215), 140.0, {}),
            ('ShaderNodeMixShader', 'Solid Mix Shader', (-200, -65), 140.0, {}),
            ('ShaderNodeMixRGB', 'Transp Mix', (-575, 95), 140.0, {'blend_type': 'MULTIPLY', 'inputs[0].default_value': 1.0}),
            ('ShaderNodeMixRGB', 'Transp Multiply 4x', (-470, 125), 140.0, {'blend_type': 'MULTIPLY', 'inputs[0].default_value': 1.0, 'inputs[2].default_value': (4.0, 4.0, 4.0, 1.0)}),
            ('ShaderNodeInvert', 'Transp Invert', (-470, 20), 140.0, {'inputs[0].default_value': 0.5}),
            ('ShaderNodeMixShader', 'Transp Mix Shader', (-205, 60), 140.0, {}),
            ('ShaderNodeBsdfTransparent', 'Transp Transparent 2', (-200, -20), 140.0, {}),
            ('ShaderNodeAddShader', 'Transp Add Shader', (-85, 65), 140.0, {}),
            ('ShaderNodeMixShader', 'Final Mix Shader', (100, 115), 140.0, {}),
            ('ShaderNodeMixRGB', 'Transp Multiply 4x.001', (-325, 125), 140.0, {'blend_type': 'MULTIPLY', 'inputs[0].default_value': 1.0, 'inputs[2].default_value': (4.0, 4.0, 4.0, 1.0)}),
            ('ShaderNodeGamma', 'Transp Gamma', (-400, 15), 140.0, {'inputs[1].default_value': 20.0}),
            ('ShaderNodeBsdfTransparent', 'Transparent BSDF', (-325, 15), 140.0, {})
        ],
        'connections': [
            ('Final Mix Shader', 0, 'Material Output', 0),
            ('Image Texture', 1, 'Compare Alpha', 0),
            ('Image Texture', 0, 'Solid Mix', 1),
            ('Attribute', 0, 'Solid Mix', 2),
            ('Solid Mix', 0, 'Solid Multiply 4x', 1),
            ('Image Texture', 1, 'Solid Invert', 1),
            ('Solid Invert', 0, 'Solid Mix Shader', 0),
            ('Solid Multiply 4x', 0, 'Solid Mix Shader', 1),
            ('Solid Transparent BSDF', 0, 'Solid Mix Shader', 2),
            ('Image Texture', 0, 'Transp Mix', 1),
            ('Attribute', 0, 'Transp Mix', 2),
            ('Transp Mix', 0, 'Transp Multiply 4x', 1),
            ('Image Texture', 1, 'Transp Invert', 1),
            ('Transp Multiply 4x.001', 0, 'Transp Mix Shader', 1),
            ('Transparent BSDF', 0, 'Transp Mix Shader', 2),
            ('Transp Mix Shader', 0, 'Transp Add Shader', 0),
            ('Transp Transparent 2', 0, 'Transp Add Shader', 1),
            ('Compare Alpha', 0, 'Final Mix Shader', 0),
            ('Solid Mix Shader', 0, 'Final Mix Shader', 1),
            ('Transp Add Shader', 0, 'Final Mix Shader', 2),
            ('Transp Multiply 4x', 0, 'Transp Multiply 4x.001', 1),
            ('Transp Invert', 0, 'Transp Gamma', 0),
            ('Transp Gamma', 0, 'Transparent BSDF', 0)
        ]
    },
    'SUBTRACTIVE': {
        'nodes': [
            ('ShaderNodeAttribute', 'Attribute', (-800, -50), 140.0, {'attribute_name': 'Color'}),
            ('ShaderNodeOutputMaterial', 'Material Output', (230, 30), 140.0, {'is_active_output': True}),
            ('ShaderNodeMath', 'Compare Alpha', (-650, 100), 140.0, {'operation': 'LESS_THAN', 'inputs[1].default_value': 0.999}),
            ('ShaderNodeMixShader', 'Final Mix Shader', (-5, 25), 140.0, {}),
            ('ShaderNodeMixRGB', 'Solid Mix', (-650, -65), 140.0, {'blend_type': 'MULTIPLY', 'inputs[0].default_value': 1.0}),
            ('ShaderNodeMixRGB', 'Solid Multiply 4x', (-450, -65), 140.0, {'blend_type': 'MULTIPLY', 'inputs[0].default_value': 1.0, 'inputs[2].default_value': (4.0, 4.0, 4.0, 1.0)}),
            ('ShaderNodeInvert', 'Solid Invert', (-450, 55), 140.0, {'inputs[0].default_value': 1.0}),
            ('ShaderNodeBsdfTransparent', 'Transparent BSDF', (-275, -100), 140.0, {}),
            ('ShaderNodeMixShader', 'Solid Mix Shader', (-150, -65), 140.0, {}),
            ('ShaderNodeMixRGB', 'Transp Mix', (-650, 15), 140.0, {'blend_type': 'MULTIPLY', 'inputs[0].default_value': 1.0}),
            ('ShaderNodeMixRGB', 'Transp Multiply 4x', (-450, 15), 140.0, {'blend_type': 'MULTIPLY', 'inputs[0].default_value': 1.0, 'inputs[2].default_value': (4.0, 4.0, 4.0, 1.0)}),
            ('ShaderNodeBsdfTransparent', 'Transp Transparent', (-150, -30), 140.0, {}),
            ('ShaderNodeInvert', 'Transp Invert 2', (-350, 15), 140.0, {'inputs[0].default_value': 1.0}),
            ('ShaderNodeGamma', 'Gamma', (-275, 15), 140.0, {'inputs[1].default_value': 10.0})
        ],
        'connections': [
            ('Final Mix Shader', 0, 'Material Output', 0),
            ('Image Texture', 1, 'Compare Alpha', 0),
            ('Compare Alpha', 0, 'Final Mix Shader', 0),
            ('Image Texture', 0, 'Solid Mix', 1),
            ('Attribute', 0, 'Solid Mix', 2),
            ('Solid Mix', 0, 'Solid Multiply 4x', 1),
            ('Image Texture', 1, 'Solid Invert', 1),
            ('Solid Invert', 0, 'Solid Mix Shader', 0),
            ('Solid Multiply 4x', 0, 'Solid Mix Shader', 1),
            ('Transparent BSDF', 0, 'Solid Mix Shader', 2),
            ('Solid Mix Shader', 0, 'Final Mix Shader', 1),
            ('Image Texture', 0, 'Transp Mix', 1),
            ('Attribute', 0, 'Transp Mix', 2),
            ('Transp Mix', 0, 'Transp Multiply 4x', 1),
            ('Transp Multiply 4x', 0, 'Transp Invert 2', 1),
            ('Transp Invert 2', 0, 'Gamma', 0),
            ('Gamma', 0, 'Transp Transparent', 0),
            ('Transp Transparent', 0, 'Final Mix Shader', 2)
        ]
    },
    'HALF_TRANSPARENT': {
        'nodes': [
            ('ShaderNodeAttribute', 'Attribute', (-800, -90), 140.0, {'attribute_name': 'Color'}),
            ('ShaderNodeOutputMaterial', 'Material Output', (170, 105), 140.0, {'is_active_output': True}),
            ('ShaderNodeMath', 'Compare Alpha', (-465, 120), 140.0, {'operation': 'LESS_THAN', 'inputs[1].default_value': 0.999}),
            ('ShaderNodeMixShader', 'Final Mix Shader', (40, 110), 140.0, {'inputs[0].default_value': 0.5}),
            ('ShaderNodeMixRGB', 'Solid Mix', (-615, -95), 140.0, {'blend_type': 'MULTIPLY', 'inputs[0].default_value': 1.0}),
            ('ShaderNodeMixRGB', 'Solid Multiply 4x', (-465, -95), 140.0, {'blend_type': 'MULTIPLY', 'inputs[0].default_value': 1.0, 'inputs[2].default_value': (4.0, 4.0, 4.0, 1.0)}),
            ('ShaderNodeBsdfTransparent', 'Transparent BSDF', (-320, -80), 140.0, {}),
            ('ShaderNodeMixShader', 'Solid Mix Shader', (-115, 55), 140.0, {}),
            ('ShaderNodeMixRGB', 'Transp Mix', (-615, -25), 140.0, {'blend_type': 'MULTIPLY', 'inputs[0].default_value': 1.0}),
            ('ShaderNodeMixRGB', 'Transp Multiply 4x', (-465, -25), 140.0, {'blend_type': 'MULTIPLY', 'inputs[0].default_value': 1.0, 'inputs[2].default_value': (4.0, 4.0, 4.0, 1.0), 'use_clamp': True}),
            ('ShaderNodeInvert', 'Transp Invert', (-470, 20), 140.0, {'inputs[0].default_value': 1.0}),
            ('ShaderNodeBsdfTransparent', 'Transp Transparent', (-320, -120), 140.0, {}),
            ('ShaderNodeMixShader', 'Transp Mix Shader', (-120, -15), 140.0, {})
        ],
        'connections': [
            ('Final Mix Shader', 0, 'Material Output', 0),
            ('Image Texture', 1, 'Compare Alpha', 0),
            ('Image Texture', 0, 'Solid Mix', 1),
            ('Attribute', 0, 'Solid Mix', 2),
            ('Solid Mix', 0, 'Solid Multiply 4x', 1),
            ('Compare Alpha', 0, 'Solid Mix Shader', 0),
            ('Solid Multiply 4x', 0, 'Solid Mix Shader', 1),
            ('Transparent BSDF', 0, 'Solid Mix Shader', 2),
            ('Solid Mix Shader', 0, 'Final Mix Shader', 1),
            ('Image Texture', 0, 'Transp Mix', 1),
            ('Attribute', 0, 'Transp Mix', 2),
            ('Transp Mix', 0, 'Transp Multiply 4x', 1),
            ('Image Texture', 1, 'Transp Invert', 1),
            ('Transp Invert', 0, 'Transp Mix Shader', 0),
            ('Transp Multiply 4x', 0, 'Transp Mix Shader', 1),
            ('Transp Transparent', 0, 'Transp Mix Shader', 2),
            ('Transp Mix Shader', 0, 'Final Mix Shader', 2)
        ]
    },
    'ADDITIVE_TRANSLUCENT': {
        'nodes': [
            ('ShaderNodeAttribute', 'Attribute', (-600, 0), 140.0, {'attribute_name': 'Color'}),
            ('ShaderNodeOutputMaterial', 'Material Output', (500, 0), 140.0, {'is_active_output': True}),
            ('ShaderNodeMixRGB', 'Mix Texture Vertex', (-400, 0), 140.0, {'blend_type': 'MULTIPLY', 'inputs[0].default_value': 1.0}),
            ('ShaderNodeMixRGB', 'Multiply 4x', (-200, 0), 140.0, {'blend_type': 'MULTIPLY', 'inputs[0].default_value': 1.0, 'inputs[2].default_value': (4.0, 4.0, 4.0, 1.0)}),
            ('ShaderNodeBsdfTransparent', 'Transparent BSDF', (0, -120), 140.0, {}),
            ('ShaderNodeInvert', 'Invert Alpha', (-200, 120), 140.0, {'inputs[0].default_value': 1.0}),
            ('ShaderNodeMixShader', 'Mix Shader', (200, 0), 140.0, {}),
            ('ShaderNodeGamma', 'Gamma', (0, 120), 140.0, {'inputs[1].default_value': 10.0})
        ],
        'connections': [
            ('Image Texture', 0, 'Mix Texture Vertex', 1),
            ('Attribute', 0, 'Mix Texture Vertex', 2),
            ('Mix Texture Vertex', 0, 'Multiply 4x', 1),
            ('Multiply 4x', 0, 'Mix Shader', 1),
            ('Transparent BSDF', 0, 'Mix Shader', 2),
            ('Mix Shader', 0, 'Material Output', 0),
            ('Image Texture', 1, 'Invert Alpha', 1),
            ('Invert Alpha', 0, 'Gamma', 0),
            ('Gamma', 0, 'Mix Shader', 0)
        ]
    }
}