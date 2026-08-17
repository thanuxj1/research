$path = 'e:\research\frontend\src\SafeTravelLK_Page1.jsx'
$c = [System.IO.File]::ReadAllText($path)
$c = $c.Replace('fontSize: 11.5", lineHeight: 1.4', 'fontSize: 11.5, lineHeight: 1.4')
[System.IO.File]::WriteAllText($path, $c, [System.Text.Encoding]::UTF8)
Write-Host "Done"
