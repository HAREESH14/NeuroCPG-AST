# Phase 2 Semantic Detection Case Studies

**Total semantic detections across all models: 10**

## Summary

| Category | Count |
|----------|------:|
| invalid_type_transform | 4 |
| lost_control_dep | 7 |

| Model | Semantic Detections |
|-------|--------------------:|
| groq_llama-3.3-70b-versatile | 9 |
| ollama_qwen2.5-coder_7b | 2 |

---

## Individual Case Studies

### Case 1: 1055_shortest_way_to_form_string.c (groq_llama-3.3-70b-versatile)

- **Category**: `lost_control_dep` (×1)
- **File totals**: 1 total (0 structural, 1 semantic)
- **Confidence**: 0.1000
- **Adjudication**: `[TO FILL: TP / FP / BORDERLINE]`

<details>
<summary>C Source (28 lines)</summary>

```c
#include <stdio.h>
#include <stdlib.h>

int numPairsDivisibleBy60(int time[]);

int numPairsDivisibleBy60(int time[])
{
  int count[60];
  int pairs = 0;
  for (int _fi1 = 0; _fi1 < (sizeof(time) / sizeof(time[0])); _fi1++)
  {
    int t = time[_fi1];
    int mod = t % 60;
    pairs += count[(60 - mod) % 60];
    count[mod]++;
  }

  return pairs;
}



int main()
{
  return 0;
}



```
</details>

<details>
<summary>Java Translation (16 lines)</summary>

```java
public class Main {
  public static int numPairsDivisibleBy60(int[] time) {
    int[] count = new int[60];
    int pairs = 0;
    for (int t : time) {
      int mod = t % 60;
      pairs += count[(60 - mod) % 60];
      count[mod]++;
    }
    return pairs;
  }

  public static void main(String[] args) {
    return;
  }
}
```
</details>

**Analysis**: _[Describe the specific broken dependency edge or type transformation that Phase 2 detected. Explain why this would be invisible to structural analysis.]_

---

### Case 2: 1329_sort_the_matrix_diagonally.c (groq_llama-3.3-70b-versatile)

- **Category**: `lost_control_dep` (×1)
- **File totals**: 1 total (0 structural, 1 semantic)
- **Confidence**: 0.7000
- **Adjudication**: `[TO FILL: TP / FP / BORDERLINE]`

<details>
<summary>C Source (34 lines)</summary>

```c
#include <stdio.h>
#include <stdlib.h>
#include <math.h>

int minCostToMoveChips(int position[]);

int minCostToMoveChips(int position[])
{
  int evenCount = 0;
  int oddCount = 0;
  for (int _fi1 = 0; _fi1 < (sizeof(position) / sizeof(position[0])); _fi1++)
  {
    int i = position[_fi1];
    if ((i % 2) == 0)
    {
      evenCount++;
    }
    else
    {
      oddCount++;
    }
  }

  return fmin(evenCount, oddCount);
}



int main()
{
  return 0;
}



```
</details>

<details>
<summary>Java Translation (18 lines)</summary>

```java
public class Main {
    public static int minCostToMoveChips(int[] position) {
        int evenCount = 0;
        int oddCount = 0;
        for (int i : position) {
            if ((i % 2) == 0) {
                evenCount++;
            } else {
                oddCount++;
            }
        }
        return Math.min(evenCount, oddCount);
    }

    public static void main(String[] args) {
        return;
    }
}
```
</details>

**Analysis**: _[Describe the specific broken dependency edge or type transformation that Phase 2 detected. Explain why this would be invisible to structural analysis.]_

---

### Case 3: 135_candy.c (groq_llama-3.3-70b-versatile)

- **Category**: `lost_control_dep` (×1)
- **File totals**: 1 total (0 structural, 1 semantic)
- **Confidence**: 0.8500
- **Adjudication**: `[TO FILL: TP / FP / BORDERLINE]`

<details>
<summary>C Source (49 lines)</summary>

```c
#include <stdio.h>
#include <stdlib.h>
#include <math.h>

int minCandies(int ratings[], int ratings_len);

int minCandies(int ratings[], int ratings_len)
{
  int n = ratings_len;
  int candies[n];
  for (int i = 0; i < n; i++)
  {
    candies[i] = 1;
  }

  for (int i = 1; i < n; i++)
  {
    if (ratings[i] > ratings[i - 1])
    {
      candies[i] = candies[i - 1] + 1;
    }
  }

  for (int i = n - 2; i >= 0; i--)
  {
    if (ratings[i] > ratings[i + 1])
    {
      candies[i] = fmax(candies[i], candies[i + 1] + 1);
    }
  }

  int sum = 0;
  for (int _fi1 = 0; _fi1 < (sizeof(candies) / sizeof(candies[0])); _fi1++)
  {
    int candy = candies[_fi1];
    sum += candy;
  }

  return sum;
}



int main()
{
  return 0;
}



```
</details>

<details>
<summary>Java Translation (34 lines)</summary>

```java
import java.lang.Math;

public class Main {
  public static int minCandies(int[] ratings) {
    int n = ratings.length;
    int[] candies = new int[n];
    for (int i = 0; i < n; i++) {
      candies[i] = 1;
    }

    for (int i = 1; i < n; i++) {
      if (ratings[i] > ratings[i - 1]) {
        candies[i] = candies[i - 1] + 1;
      }
    }

    for (int i = n - 2; i >= 0; i--) {
      if (ratings[i] > ratings[i + 1]) {
        candies[i] = Math.max(candies[i], candies[i + 1] + 1);
      }
    }

    int sum = 0;
    for (int candy : candies) {
      sum += candy;
    }

    return sum;
  }

  public static void main(String[] args) {
    return;
  }
}
```
</details>

**Analysis**: _[Describe the specific broken dependency edge or type transformation that Phase 2 detected. Explain why this would be invisible to structural analysis.]_

---

### Case 4: 136_single_number.c (groq_llama-3.3-70b-versatile)

- **Category**: `lost_control_dep` (×1)
- **File totals**: 1 total (0 structural, 1 semantic)
- **Confidence**: 0.1000
- **Adjudication**: `[TO FILL: TP / FP / BORDERLINE]`

<details>
<summary>C Source (25 lines)</summary>

```c
#include <stdio.h>
#include <stdlib.h>

int singleNumber(int nums[]);

int singleNumber(int nums[])
{
  int result = 0;
  for (int _fi1 = 0; _fi1 < (sizeof(nums) / sizeof(nums[0])); _fi1++)
  {
    int num = nums[_fi1];
    result ^= num;
  }

  return result;
}



int main()
{
  return 0;
}



```
</details>

<details>
<summary>Java Translation (13 lines)</summary>

```java
public class Main {
  public static int singleNumber(int[] nums) {
    int result = 0;
    for (int num : nums) {
      result ^= num;
    }
    return result;
  }

  public static void main(String[] args) {
    return;
  }
}
```
</details>

**Analysis**: _[Describe the specific broken dependency edge or type transformation that Phase 2 detected. Explain why this would be invisible to structural analysis.]_

---

### Case 5: 1390_four_divisors.c (groq_llama-3.3-70b-versatile)

- **Category**: `lost_control_dep` (×1)
- **File totals**: 1 total (0 structural, 1 semantic)
- **Confidence**: 0.8500
- **Adjudication**: `[TO FILL: TP / FP / BORDERLINE]`

<details>
<summary>C Source (43 lines)</summary>

```c
#include <stdio.h>
#include <stdlib.h>

int sumOfFourDivisors(int nums[]);

int sumOfFourDivisors(int nums[])
{
  int sum = 0;
  for (int _fi1 = 0; _fi1 < (sizeof(nums) / sizeof(nums[0])); _fi1++)
  {
    int num = nums[_fi1];
    int count = 0;
    int div_sum = 0;
    for (int i = 1; (i * i) <= num; ++i)
    {
      if ((num % i) == 0)
      {
        count += ((i * i) == num ? 1 : 2);
        div_sum += i + (num / i);
        if (count > 4)
        {
          break;
        }
      }
    }

    if (count == 4)
    {
      sum += div_sum;
    }
  }

  return sum;
}



int main()
{
  return 0;
}



```
</details>

<details>
<summary>Java Translation (28 lines)</summary>

```java
public class Main {
  public static int sumOfFourDivisors(int[] nums) {
    int sum = 0;
    for (int num : nums) {
      int count = 0;
      int divSum = 0;
      for (int i = 1; (i * i) <= num; ++i) {
        if ((num % i) == 0) {
          count += ((i * i) == num ? 1 : 2);
          divSum += i + (num / i);
          if (count > 4) {
            break;
          }
        }
      }

      if (count == 4) {
        sum += divSum;
      }
    }

    return sum;
  }

  public static void main(String[] args) {
    return;
  }
}
```
</details>

**Analysis**: _[Describe the specific broken dependency edge or type transformation that Phase 2 detected. Explain why this would be invisible to structural analysis.]_

---

### Case 6: 1545_find_kth_bit_in_nth_binary_string.c (groq_llama-3.3-70b-versatile)

- **Category**: `invalid_type_transform` (×2)
- **File totals**: 2 total (0 structural, 2 semantic)
- **Confidence**: 0.5000
- **Adjudication**: `[TO FILL: TP / FP / BORDERLINE]`

<details>
<summary>C Source (37 lines)</summary>

```c
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

char* largestNumber(int cost[], int target);

char* largestNumber(int cost[], int target)
{
  char* dp[target + 1];
  dp[0] = "";
  for (int t = 1; t <= target; ++t)
  {
    for (int i = 1; i <= 9; ++i)
    {
      if ((t >= cost[i - 1]) && (dp[t - cost[i - 1]] != NULL))
      {
        char* temp = dp[t - cost[i - 1]] + i;
        if ((dp[t] == NULL) || (dp[t] <= strlen(temp)))
        {
          dp[t] = temp;
        }
      }
    }

  }

  return (dp[target] == NULL ? "0" : dp[target]);
}



int main()
{
  return 0;
}



```
</details>

<details>
<summary>Java Translation (21 lines)</summary>

```java
public class Main {
    public static String largestNumber(int[] cost, int target) {
        String[] dp = new String[target + 1];
        dp[0] = "";
        for (int t = 1; t <= target; ++t) {
            for (int i = 1; i <= 9; ++i) {
                if ((t >= cost[i - 1]) && (dp[t - cost[i - 1]] != null)) {
                    String temp = dp[t - cost[i - 1]] + i;
                    if ((dp[t] == null) || (dp[t].length() < temp.length() || (dp[t].length() == temp.length() && dp[t].compareTo(temp) < 0))) {
                        dp[t] = temp;
                    }
                }
            }
        }
        return (dp[target] == null ? "0" : dp[target]);
    }

    public static void main(String[] args) {
        return;
    }
}
```
</details>

**Analysis**: _[Describe the specific broken dependency edge or type transformation that Phase 2 detected. Explain why this would be invisible to structural analysis.]_

---

### Case 7: 1615_maximal_network_rank.c (groq_llama-3.3-70b-versatile)

- **Category**: `invalid_type_transform` (×1)
- **File totals**: 1 total (0 structural, 1 semantic)
- **Confidence**: 0.6667
- **Adjudication**: `[TO FILL: TP / FP / BORDERLINE]`

<details>
<summary>C Source (39 lines)</summary>

```c
#include <stdio.h>
#include <stdlib.h>

int rangeSum(int nums[], int n, int left, int right);

int rangeSum(int nums[], int n, int left, int right)
{
  int MOD = ((int) 1e9) + 7;
  int sums[(n * (n + 1)) / 2];
  int index = 0;
  for (int i = 0; i < n; ++i)
  {
    int sum = 0;
    for (int j = i; j < n; ++j)
    {
      sum += nums[j];
      sums[index++] = sum;
    }

  }

  sort(sums);
  int result = 0;
  for (int i = left - 1; i < right; ++i)
  {
    result = (result + sums[i]) % MOD;
  }

  return result;
}



int main()
{
  return 0;
}



```
</details>

<details>
<summary>Java Translation (27 lines)</summary>

```java
import java.util.Arrays;
import java.util.Scanner;

public class Main {
  public static int rangeSum(int[] nums, int n, int left, int right) {
    int MOD = (int) 1e9 + 7;
    int[] sums = new int[(n * (n + 1)) / 2];
    int index = 0;
    for (int i = 0; i < n; ++i) {
      int sum = 0;
      for (int j = i; j < n; ++j) {
        sum += nums[j];
        sums[index++] = sum;
      }
    }
    Arrays.sort(sums);
    int result = 0;
    for (int i = left - 1; i < right; ++i) {
      result = (result + sums[i]) % MOD;
    }
    return result;
  }

  public static void main(String[] args) {
    return;
  }
}
```
</details>

**Analysis**: _[Describe the specific broken dependency edge or type transformation that Phase 2 detected. Explain why this would be invisible to structural analysis.]_

---

### Case 8: 1627_graph_connectivity_with_threshold.c (groq_llama-3.3-70b-versatile)

- **Category**: `lost_control_dep` (×1)
- **File totals**: 1 total (0 structural, 1 semantic)
- **Confidence**: 0.5500
- **Adjudication**: `[TO FILL: TP / FP / BORDERLINE]`

<details>
<summary>C Source (33 lines)</summary>

```c
#include <stdio.h>
#include <stdlib.h>
#include <math.h>

int lastMoment(int n, int left[], int right[]);

int lastMoment(int n, int left[], int right[])
{
  int max_left = 0;
  int min_right = n;
  for (int _fi1 = 0; _fi1 < (sizeof(left) / sizeof(left[0])); _fi1++)
  {
    int position = left[_fi1];
    max_left = fmax(max_left, position);
  }

  for (int _fi2 = 0; _fi2 < (sizeof(right) / sizeof(right[0])); _fi2++)
  {
    int position = right[_fi2];
    min_right = fmin(min_right, position);
  }

  return fmax(max_left, n - min_right);
}



int main()
{
  return 0;
}



```
</details>

<details>
<summary>Java Translation (19 lines)</summary>

```java
public class Main {
    public static int lastMoment(int n, int[] left, int[] right) {
        int max_left = 0;
        int min_right = n;
        for (int position : left) {
            max_left = Math.max(max_left, position);
        }

        for (int position : right) {
            min_right = Math.min(min_right, position);
        }

        return Math.max(max_left, n - min_right);
    }

    public static void main(String[] args) {
        return;
    }
}
```
</details>

**Analysis**: _[Describe the specific broken dependency edge or type transformation that Phase 2 detected. Explain why this would be invisible to structural analysis.]_

---

### Case 9: 1598_crawler_log_folder.c (ollama_qwen2.5-coder_7b)

- **Category**: `lost_control_dep` (×1)
- **File totals**: 2 total (0 structural, 2 semantic)
- **Confidence**: 0.5250
- **Adjudication**: `[TO FILL: TP / FP / BORDERLINE]`

<details>
<summary>C Source (35 lines)</summary>

```c
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <math.h>

int minOperations(char* logs[]);

int minOperations(char* logs[])
{
  int depth = 0;
  for (int _fi1 = 0; _fi1 < (sizeof(logs) / sizeof(logs[0])); _fi1++)
  {
    char* log = logs[_fi1];
    if (strcmp(log, "../") == 0)
    {
      depth = fmax(0, depth - 1);
    }
    else
      if (strcmp(log, "./") == 0)
    {
      depth += 1;
    }
  }

  return depth;
}



int main()
{
  return 0;
}



```
</details>

<details>
<summary>Java Translation (25 lines)</summary>

```java
import java.util.Scanner;

public class MinOperations {

    public static int minOperations(String[] logs) {
        int depth = 0;
        for (String log : logs) {
            if ("../".equals(log)) {
                depth = Math.max(0, depth - 1);
            } else if ("./".equals(log)) {
                depth += 1;
            }
        }

        return depth;
    }

    public static void main(String[] args) {
        Scanner scanner = new Scanner(System.in);
        // Example usage
        String[] logs = {"../", "./", "folder"};
        int result = minOperations(logs);
        System.out.println(result);
    }
}
```
</details>

**Analysis**: _[Describe the specific broken dependency edge or type transformation that Phase 2 detected. Explain why this would be invisible to structural analysis.]_

---

### Case 10: 1598_crawler_log_folder.c (ollama_qwen2.5-coder_7b)

- **Category**: `invalid_type_transform` (×1)
- **File totals**: 2 total (0 structural, 2 semantic)
- **Confidence**: 0.5250
- **Adjudication**: `[TO FILL: TP / FP / BORDERLINE]`

<details>
<summary>C Source (35 lines)</summary>

```c
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <math.h>

int minOperations(char* logs[]);

int minOperations(char* logs[])
{
  int depth = 0;
  for (int _fi1 = 0; _fi1 < (sizeof(logs) / sizeof(logs[0])); _fi1++)
  {
    char* log = logs[_fi1];
    if (strcmp(log, "../") == 0)
    {
      depth = fmax(0, depth - 1);
    }
    else
      if (strcmp(log, "./") == 0)
    {
      depth += 1;
    }
  }

  return depth;
}



int main()
{
  return 0;
}



```
</details>

<details>
<summary>Java Translation (25 lines)</summary>

```java
import java.util.Scanner;

public class MinOperations {

    public static int minOperations(String[] logs) {
        int depth = 0;
        for (String log : logs) {
            if ("../".equals(log)) {
                depth = Math.max(0, depth - 1);
            } else if ("./".equals(log)) {
                depth += 1;
            }
        }

        return depth;
    }

    public static void main(String[] args) {
        Scanner scanner = new Scanner(System.in);
        // Example usage
        String[] logs = {"../", "./", "folder"};
        int result = minOperations(logs);
        System.out.println(result);
    }
}
```
</details>

**Analysis**: _[Describe the specific broken dependency edge or type transformation that Phase 2 detected. Explain why this would be invisible to structural analysis.]_

---
