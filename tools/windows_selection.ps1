param([long]$WindowHandle)
$ErrorActionPreference='Stop'
[Console]::OutputEncoding=[System.Text.UTF8Encoding]::new($false)
Add-Type -AssemblyName UIAutomationClient
Add-Type -AssemblyName UIAutomationTypes
$root=[System.Windows.Automation.AutomationElement]::FromHandle([IntPtr]$WindowHandle)
$focused=[System.Windows.Automation.AutomationElement]::FocusedElement
$result=@{text='';context='';source=$root.Current.Name}
$candidates=[System.Collections.Generic.List[object]]::new()
$node=$focused
for($i=0;$i -lt 6 -and $null -ne $node;$i++) {
  try {
    if($node.Current.ProcessId -ne $root.Current.ProcessId){break}
    $candidates.Add($node)
    $node=[System.Windows.Automation.TreeWalker]::ControlViewWalker.GetParent($node)
  } catch {break}
}
$candidates.Add($root)
function Read-Selection($elements) {
 foreach($item in $elements) {
  if($null -eq $item){continue}
  try {
    if($item.Current.IsPassword){continue}
    $pattern=$item.GetCurrentPattern([System.Windows.Automation.TextPattern]::Pattern)
    foreach($range in $pattern.GetSelection()) {
      $text=$range.GetText(2000)
      if([string]::IsNullOrWhiteSpace($text)){continue}
      $context=$range.Clone()
      $context.ExpandToEnclosingUnit([System.Windows.Automation.TextUnit]::Paragraph)
      $result.text=$text;$result.context=$context.GetText(6000)
      $result.bounds=@($range.GetBoundingRectangles())
      return $true
    }
  } catch {}
 }
 return $false
}
if(-not (Read-Selection $candidates)) {
 try {
  $condition=[System.Windows.Automation.PropertyCondition]::new([System.Windows.Automation.AutomationElement]::IsTextPatternAvailableProperty,$true)
  $items=$root.FindAll([System.Windows.Automation.TreeScope]::Descendants,$condition)
  $fallback=[System.Collections.Generic.List[object]]::new()
  for($i=0;$i -lt [Math]::Min(80,$items.Count);$i++){$fallback.Add($items[$i])}
  $null=Read-Selection $fallback
 } catch {}
}
$result | ConvertTo-Json -Compress
