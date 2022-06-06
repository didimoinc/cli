<a name="2.3.0"></a>
## 2.3.0 (2022-06-06)


#### New features

*   CLI is now compatible with multiple DGP versions (it will adapt to each DGP based on the selected API Key)
*   The expected didimo generated cost is now presented before the actual generation process starts executing
*   It's now possible to use a didimo package (instead of the DMX) as the input to the deformer actions


<a name="2.2.0"></a>
## 2.2.0 (2022-05-12)


#### New features

*   It's now possible to generate full-body didimos with no garments (through the none garment option)
*   Extended timeout for hair and vertex deformation actions


<a name="2.1.1"></a>
## 2.1.1 (2022-04-01)


#### Bug fixes

*   Fixed gender automatic detection value: "" -> "auto"


<a name="2.1.0"></a>
## 2.1.0 (2022-04-01)


#### New features

*   Added new options to control bodies:
  * avatar_structure: "head-only" (default) or "full-body"
  * garment: "casual" (default), "sporty"
  * gender: "" (default - triggers automatic detection), "female", "male"


<a name="2.0.3"></a>
## 2.0.3 (2022-02-03)


#### Bug fixes

*   Fixed package downloads naming conventions
*   Multiple fixes on help messages and documentation


<a name="2.0.2"></a>
## 2.0.2 (2022-01-18)


#### New features

*   Added package type to download



<a name="2.0.1"></a>
## 2.0.1 (2022-01-14)


#### Security Fixes

*   CVE-2021-33503



<a name="2.0.0"></a>
## 2.0.0 (2021-09-29)


#### Bug Fixes

*   Updated API to v3.
*   Updated feature and output compatibility to DGP 2.5.0.
*   Added support for new fitting services.



<a name="1.0.3"></a>
## 1.0.3 (2021-05-18)


#### Bug Fixes

*   Use package type as download identifier ((5e7b6622))



<a name="1.0.2"></a>
## 1.0.2 (2021-01-11)


#### Bug Fixes

*   Handle new status responses correctly ((fbd00722))



