$path = 'e:\research\frontend\src\SafeTravelLK_Page1.jsx'
$c = [System.IO.File]::ReadAllText($path)
# Fix literal \n in closing tags
$c = $c.Replace("                  })}\\n                </div>", "                  })}
                </div>")
[System.IO.File]::WriteAllText($path, $c, [System.Text.Encoding]::UTF8)
Write-Host "Done"
