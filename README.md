# Textual Diff View

Currently a WIP. 

Textual Diff View is a [Textual]https://github.com/textualize/textual) widget to display beautiful diffs in your terminal applications (TUIs).

Originally built for [Toad](https://github.com/batrachianai/toad), Textual Diff View may be used standalone.

## Screenshots

<table>
<tr>  
<td>
  
![Split dark](images/split_dark.png)

</td>
<td>
  
![Unified dark](images/unified_dark.png)

</td>
</tr>

<tr>
<td>
  
![spliut light](images/split_light.png)

</td>

<td>
  
![Unified light](images/unified_light.png)

</td>

</tr>
</table>

## Features

The `DiffView` widget displays two version of a file, and highlights the changed lines.
It will also highlight the changes within a line.

There are two layout options; a *unified* view which shows the two files top-to-bottom with highlights, and a *split* view which shoiws the two files next to each other.

Deleted lines are shown with a red highlight, and added lines are shown with a green highlight, both on top of syntax highlighting.
