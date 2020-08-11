
import ast
import vtk, slicer

class NeuroSegmentParcellationVisitor(ast.NodeVisitor):
  """
  ast NodeVisitor subclass that parses a query string to create the specified input and output MRML Nodes.
  All input/output/tool nodes are added to the parameter node references, and existing input/output/tool node references are removed.

  Basic format uses the following syntax:
    _DistanceWeightingFunction = "func" # Set the distance weighting function to use for all curve markups following this point
    _Planes = [...] # Create or retrieve all vtkMRMLMarkupPlaneNode with the speicified names in the scene
    _Curves = [...] # Create or retrieve all vtkMRMLMarkupsCurveNode with the speicified names in the scene
    _ClosedCurves = [...] # Create or retrieve all vtkMRMLMarkupsClosedCurveNode with the speicified names in the scene
    XYZ = A || B || C # Create a vtkMRMLDynamicModelerNode using the "BoundaryCut" tool, and output vtkMRMLModelNode with the name "XYZ", using markups A, B and C
  """

  def __init__(self, logic):
    self.parameterNode = None
    self.logic = logic

  def setParameterNode(self, parameterNode):
    self.parameterNode = parameterNode

  def visit_Assign(self, node):
    """
    Visit assignment operator node.
    node.target = node.value
    """

    if len(node.targets) > 1:
        logging.error("Invalid assignment in line %d" % node.lineno)
        return

    if 'target' in node._fields:
      target = node.target
    if 'targets' in node._fields:
      target = node.targets[0]

    # We currently don't perform assignments to anything except basic names.
    if not isinstance(target, ast.Name):
      logging.error("Invalid assignment in line %d" % node.lineno)
      return

    if target.id == "_Planes":
      self.process_InputNodes(node.value, "vtkMRMLMarkupsPlaneNode")
      return
    elif target.id == "_Curves":
      curveNodes = self.process_InputNodes(node.value, "vtkMRMLMarkupsCurveNode")
      for curveNode in curveNodes:
        curveNode.SetCurveTypeToShortestDistanceOnSurface()
      return
    elif target.id == "_ClosedCurves":
      curveNodes = self.process_InputNodes(node.value, "vtkMRMLMarkupsClosedCurveNode")
      for curveNode in curveNodes:
        curveNode.SetCurveTypeToShortestDistanceOnSurface()
      return
    elif target.id == "_DistanceWeightingFunction":
      self.distanceWeightingFunction = node.value.s
      return

    nodes = self.visit(node.value)

    outputModel = slicer.util.getFirstNodeByClassByName("vtkMRMLModelNode", target.id)
    if outputModel is None:
      outputModel = slicer.mrmlScene.AddNewNodeByClass("vtkMRMLModelNode", target.id)
    outputModelDisplayNode = outputModel.GetDisplayNode()
    if outputModelDisplayNode is None:
      outputModel.CreateDefaultDisplayNodes()
      outputModelDisplayNode = outputModel.GetDisplayNode()
      outputModelDisplayNode.SetVisibility(False)
    self.parameterNode.AddNodeReferenceID(self.logic.OUTPUT_MODEL_REFERENCE, outputModel.GetID())

    inputSeed = slicer.util.getFirstNodeByClassByName("vtkMRMLMarkupsFiducialNode", target.id + "_SeedPoints")
    if inputSeed is None:
      inputSeed = slicer.mrmlScene.AddNewNodeByClass("vtkMRMLMarkupsFiducialNode", target.id + "_SeedPoints")
      inputSeed.CreateDefaultDisplayNodes()

    toolNode = slicer.util.getFirstNodeByClassByName("vtkMRMLModelNode", outputModel.GetName() + "_BoundaryCut")
    if toolNode is None:
      toolNode = slicer.mrmlScene.AddNewNodeByClass("vtkMRMLDynamicModelerNode", outputModel.GetName() + "_BoundaryCut")
    toolNode.SetToolName(slicer.vtkSlicerDynamicModelerBoundaryCutTool().GetName())
    toolNode.SetNodeReferenceID(self.logic.BOUNDARY_CUT_OUTPUT_MODEL_REFERENCE, outputModel.GetID())
    toolNode.SetNodeReferenceID(self.logic.BOUNDARY_CUT_INPUT_SEED_REFERENCE, inputSeed.GetID())
    for inputNode in nodes:
      toolNode.AddNodeReferenceID(self.logic.BOUNDARY_CUT_INPUT_BORDER_REFERENCE, inputNode.GetID())
    toolNode.ContinuousUpdateOff()
    self.parameterNode.AddNodeReferenceID(self.logic.TOOL_NODE_REFERENCE, toolNode.GetID())

  def process_InputNodes(self, node, className):
    """
    Process the creation of many MRML nodes of a specific type, given an ast List node.
    :param node: ast.List representing all of the node names to be created
    :param className: String representing the class of the MRML nodes to be created
    :return: List of created nodes
    """

    if not isinstance(node, ast.List):
      logging.error("Expected list of planes in line %d" % node.lineno)
      return

    planeNames = [e.id for e in node.elts]
    inputNodes = []
    for name in planeNames:
      inputNode = slicer.util.getFirstNodeByClassByName(className, name)      
      if not inputNode:
        inputNode = slicer.mrmlScene.AddNewNodeByClass(className, name)
        inputNode.CreateDefaultDisplayNodes()
        displayNode = inputNode.GetDisplayNode()
        if displayNode:
          displayNode.SetGlyphScale(4.0)
          if className == "vtkMRMLMarkupsPlaneNode":
            displayNode.HandlesInteractiveOn()

      # Update the distance weighting parameter based on the current distance weighting function
      if inputNode.IsA("vtkMRMLMarkupsCurveNode"):
        inputNode.SetAttribute("DistanceWeightingFunction", self.distanceWeightingFunction)
      inputNodes.append(inputNode)
      self.parameterNode.AddNodeReferenceID(self.logic.INPUT_MARKUPS_REFERENCE, inputNode.GetID())
    return inputNodes

  def visit_Name(self, node):
    """
    Return the name of the current node in a list
    :param node: ast.Name for the current node
    :return: Node name in a simple list, ex: [NodeName]
    """
    slicerNode = slicer.util.getNode(node.id)
    return [slicerNode]

  def visit_Call(self, node):
    """
    Not handled currently
    """
    pass

  def visit_BinOp(self, node):
    """
    :param node: Input ast binary operator node
    :return: List of names combined from left and right nodes
    """

    leftValue = node.left
    rightValue = node.right
    if leftValue == None or rightValue == None:
      logging.error("Invalid binary operator arguments!")
      return

    # Both left and right nodes are assumed to contain lists
    leftNodes = self.visit(leftValue)
    rightNodes = self.visit(rightValue)
    return leftNodes + rightNodes

  def visit_UnaryOp(self, node):
    """
    Not handled currently
    """
    logging.error("Unary operator not supported!")