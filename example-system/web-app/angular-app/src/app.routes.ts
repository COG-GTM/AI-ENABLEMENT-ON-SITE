import { Routes } from "@angular/router";
import { RequestFormComponent } from "./request-form.component";
import { RequestListComponent } from "./request-list.component";
import { RequestDetailComponent } from "./request-detail.component";

// walkthrough:angular-router:start
export const routes: Routes = [
  { path: "", component: RequestListComponent },
  { path: "requests/new", component: RequestFormComponent },
  { path: "requests/:id", component: RequestDetailComponent },
  { path: "**", redirectTo: "" }
];
// walkthrough:angular-router:end
