We need to change how timeline is graphed completely.
The timeline should scroll vertically.
Each model line should have the label on top like a table. Labels should be only model name avoid provider. 
Models get a color assigned, a migration should assign colors to models without a color. 
So create a table of colors in the db with a relation to the models that is 1 to 1.
Colors are assigned in order to the first available, if a provider is deleted the color is free.
Use this colors R G B
tableau20 = [(31, 119, 180), (174, 199, 232), (255, 127, 14), (255, 187, 120),  
             (44, 160, 44), (152, 223, 138), (214, 39, 40), (255, 152, 150),  
             (148, 103, 189), (197, 176, 213), (140, 86, 75), (196, 156, 148),  
             (227, 119, 194), (247, 182, 210), (127, 127, 127), (199, 199, 199),  
             (188, 189, 34), (219, 219, 141), (23, 190, 207), (158, 218, 229)]  
Then  this is how the timeline will render. 
We have the lines going from top to bottom old to new.
We preserve the line background guide.
Dots become rectangles with the short description
We preserve the month lines but disable zoom capability.
Each month line should have a label
Labels of month go to the left of the lines. Short 3 letter month + 4 digit year.
we should have the short description of the events per model inside each model line/column.
a slightly  rounded rectangle of 149px width 92px height that shows the short description of the event clipped to what it fits inside this rectangle. Content is centered. The rectangle should have a border of the color of the source of 2px width rounded borders.
Zoom does not exist in this one. 
Fitting is as follows:
Each month check the max events for a single provider in that month to calculate the month height and adds some padding (4px)
Empty months take same as single event months.
Inside the month events are put in order, centered to the position of the day (i.e. if we have 1000px 1st is 0px, 30th or last is 1000px-92px+padding approx. So if a provider has 10 elements the 3 elements or the other provider are approximatedly aligned to the time but we don't waste space. Do a reasonable effort, don't go crazy.
If a event is clicked is goes like now to the full description.
The whole timeline is centered in screen, add invisible compensation to the right of the timeline so the month labels are like left of the timeline and the timeline is centered. Else it would look not centered because of the labels.
For now don't touch current timeline, this should be a new view directly called "Linea de tiempo" as a tab.
You can put all the javascript of it in a .js file so index.html is not crowded.
